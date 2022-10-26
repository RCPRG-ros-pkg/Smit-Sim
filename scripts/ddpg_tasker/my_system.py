import gym
import random
import numpy as np
import sys
from datetime import datetime, timedelta, date, time
import math as m
sys.path.insert(0, '../')
from linear_path_ROS_planner import ROSNavigation
sys.path.insert(0, '../../../tasker/src/TaskER/')
from RequestTable import RequestTable, ScheduleRules, ScheduleRule, TaskerReqest

class SystemConfig(object):
  def __init__(self):
    self.robot_speed = 0.1

    # self.reward_existing_task = 1
    # self.reward_finish_task = 2
    self.reward_finish_all = 10

    # self.penalty_switch = 2
    # self.penalty_wrong_task = 10
    self.penalty_dead = 20

    self.dt = timedelta(seconds = 15)
    self.time_horizon = timedelta(hours = 1)
    self.now = datetime.combine(date.today(), time(15, 0))
    self.time_slot = timedelta(minutes = 15)
    self.recalculation_time = timedelta(minutes = (5))

    # self.weight_estimate = 1.0
    # self.weight_distance = 1.0
    # self.weight_current = 1.0

    self.save = False
    self.prefix = ""


class System(gym.Env):
  def __init__(self, task_config, config = SystemConfig(), random_state = -1):
    self.config = config
    self.task_config = task_config
    self.tasks = []
    self.dt = self.config.dt
    self.now = self.config.now
    
    # self.penalty = penalty
    # self.max_steps = 2*self.config.time_horizon.seconds/self.config.recalculation_time
    self.save = config.save
    self.random_state = random_state
    if random_state >= 0:
      self.fix_random = True
    else:
      self.fix_random = False

    self.N = task_config.count
    self.slot_num = int(self.config.time_horizon/self.config.time_slot)
    state_shape = (4 + 3 * self.slot_num)
    self.state = np.zeros(state_shape)
    self.state_space = gym.spaces.Box(low=0, high=100, shape=(state_shape,))
    self.action_space = gym.spaces.Box(low = 0, high = 1, shape = (2,))

    self.navigator = ROSNavigation()
    self.reset()


  # def render(self, mode="save"):
  #   if (mode=="human" or mode=="save") and self.save:
  #     out = f"{self.selected};{self.pos[0]};{self.pos[1]};"
  #     for i,t in enumerate(self.tasks):
  #       t_id = i // self.N
  #       t_no = i % self.N
  #       out = out + f"{t_id};{t_no};{t.do_estimate()};{t.pos[0]};{t.pos[1]};{t.serialize()};"
  #     self.file_out.write(out + "\n")
  #   elif mode == "ansi":
  #     arr = []
  #     for i in range(20):
  #       arr.append([-1] * 20)
  #     for i,t in enumerate(self.tasks):
  #       t_id = i // self.N
  #       t_no = i % self.N
  #       print(t_id, t_no, t)

  #       if t.do_estimate() > 0:
  #         x = int(t.pos[0] * 2)
  #         y = int(t.pos[1] * 2)
  #         arr[x][y] = t_id

  #     x = int(self.pos[0] * 2)
  #     y = int(self.pos[1] * 2)
  #     arr[x][y] += 100

  #     for r in arr:
  #       for c in r:
  #         if c >= 50:
  #           print('>', end='')
  #           c = c - 100
  #         else:
  #           print(' ', end='')

  #         if c >= 0:
  #           print(str(c%100), end='')
  #         else:
  #           print('.', end='')
  #       print('')

  def close(self):
    if self.save:
      self.file_out.close()

  def reset(self):
    self.selected = -1
    # self.steps = 0
    self.now = self.config.now
    self.tasks = self.task_config.generate()

    # initial agent position
    x_min = 0
    x_max = 10
    y_min = 0
    y_max = 10
    x1 = x_min + random.random() * (x_max - x_min)
    y1 = y_min + random.random() * (y_max - y_min)
    self.pos = np.array([x1, y1])
    self.area = x_max * y_max

    # initialize tasker
    self.rt = RequestTable()
    self.jobs = []
    for i, t in enumerate(self.tasks):
      sr = ScheduleRules()
      sr.addRule(ScheduleRule(rule_type='at', rule_value=t.getDeadline()))
      job = TaskerReqest(ID=t.getID(),huid=t.getUUID(), plan_args='', req_time=self.now, shdl_rules=sr, priority=t.getPriority())
      job.set_burst_time(t.getBurst() + timedelta(seconds = self.navigator.plan(self.pos, t.pos).get_distance() / self.config.robot_speed))
      job.evaluate_rules()
      self.rt.addRecord(job)
      self.jobs.append(job)
    self.out, self.profit = self.rt.schedule_with_priority()

    # initialize state
    self.proccesed = 0
    self.state = np.zeros(4 + 3 * self.slot_num)
    self.state[0:4] = [
      self.jobs[self.proccesed].priority,
      m.log(self.jobs[self.proccesed].burst_time.seconds, self.config.time_horizon.seconds),
      np.tanh((self.jobs[self.proccesed].start_time - self.now).seconds/self.config.time_horizon.seconds),
      (self.jobs[self.proccesed].burst_time.seconds - self.tasks[self.proccesed].getBurst().seconds) * self.config.robot_speed/self.area
    ]

    for s in range(4):
      start = self.now + s*self.config.time_slot
      stop = self.now + (s+1)*self.config.time_slot
      for i,j in enumerate(self.jobs):
        if j.start_time >= start and j.start_time < stop or j.deadline > start and j.deadline <= stop or j.start_time < start and j.deadline > stop:
          self.state[4+s*3] += j.priority
          self.state[6+s*3] += 1
      for i,j in enumerate(self.out.scheduled):
        if j.start >= start and j.start < stop or j.stop > start and j.stop <= stop or j.start < start and j.stop > stop:
          self.state[5+s*3] += self.rt.get_request(j.jobID).priority

    print("Reset")
    print(self.state)
  
    self.fname = ""
    if self.save:
      now = datetime.now() # current date and time
      fname = self.config.prefix + now.strftime(f"%Y%m%d_%H%M%S_%f_{self.task_config.seed}.csv")
      self.fname = fname
      self.file_out = open(fname, "w")

    return self.state

  # def do_step(self, action):
  #   new_state = np.zeros_like(self.state)
  #   self.steps = self.steps + 1
  #   for i,t in enumerate(self.tasks):
  #     t_id = i // self.N
  #     t_no = i % self.N

  #     if i == action:
  #       time_left = self.dt

  #       # do the actual travel to the action spot if distanse from the agent is greater than threshold
  #       if t.dist(self.pos) > 0.5:
  #         path = self.navigator.plan(self.pos, t.pos)
  #         [self.pos, time_left] = path.step(self.config.robot_speed, self.dt)

  #         # force the whole step wait
  #         time_left = 0

  #         # task waits when the agent moves
  #         t.do_wait(self.dt - time_left)

  #       # travel took less than single time step - do part of the task
  #       if time_left > 0:
  #         t.do_work(time_left)
  #         self.pos = t.updatePos(self.pos)

  #       # task finished
  #       if t.do_estimate() <= 0:
  #           self.selected = -1
  #     else:
  #       t.do_wait(self.dt)

  #     new_state[t_id, t_no, 0] = t.do_estimate()
  #     new_state[t_id, t_no, 1] = t.dist(self.pos)

  #   return new_state

  def do_step_until(self, deadline):

    if self.now >= deadline:
      return

    for i,j in enumerate(self.out.scheduled):

      if j.start <= self.now and j.stop > self.now:

        # if task is done remove it from TaskER
        if not self.tasks[j.jobID].do_estimate():
          self.rt.removeRecord_by_id(j.jobID)
          return

        time_left = self.dt.seconds

        # do the actual travel to the action spot if distanse from the agent is greater than threshold
        if self.tasks[j.jobID].dist(self.pos) > 0.1:
          path = self.navigator.plan(self.pos, t.pos)
          [self.pos, time_left] = path.step(self.config.robot_speed, time_left)

        # work on a task
        if time_left > 0:
          self.tasks[j.jobID].do_work(time_left)
          self.pos = self.tasks[j.jobID].pos

        # update time
        self.now = self.now + self.dt

        # if task is done remove it from TaskER
        if not self.tasks[j.jobID].do_estimate():
          self.rt.removeRecord_by_id(j.jobID)
          return

        # continue work
        self.do_step_until(deadline)

  def is_alive(self):
    for t in self.tasks:
      if not t.is_alive():
        return False

    return True

  def all_done(self):
    for t in self.tasks:
      if t.do_estimate():
        return False
      return True

  def do_step(self):
    self.proccesed += 1
    if self.proccesed > self.jobs[-1].getID():
      self.proccesed = 0
      self.steps += 1
      self.do_step_until(self.now + self.recalculation_time)
    if not self.tasks[self.proccesed].do_estimate():
      self.do_step()

  def step(self, action):
    self.jobs[self.proccesed].priority = action[0]
    burst = self.tasks[self.proccesed].getBurst() + timedelta(seconds = self.navigator.plan(self.pos, self.tasks[self.proccesed].pos).get_distance() / self.config.robot_speed)
    self.jobs[self.proccesed].start_time = self.now + action[1]*self.config.time_horizon
    self.jobs[self.proccesed].deadline = self.jobs[self.proccesed].start_time + burst
    self.jobs[self.proccesed].burst_time = burst

    self.rt.updateRecord(self.jobs[self.proccesed])
    self.out, self.profit = self.rt.schedule_with_priority()

    if not self.is_alive():
      done = True
      reward = -self.config.penalty_dead
      status = "DEAD"
    elif self.now > self.config.now + 2 * self.config.time_horizon:
      done = True
      reward = -self.config.penalty_dead
      status = "TIME"
    elif self.all_done():
      done = True
      reward = self.config.reward_finish_all
      status = "DONE"
    else:
      self.do_step()

      self.state = np.zeros(4 + 3 * self.slot_num)
      self.state[0:4] = [
        self.jobs[self.proccesed].priority,
        m.log(self.jobs[self.proccesed].burst_time.seconds, self.config.time_horizon.seconds),
        np.tanh((self.jobs[self.proccesed].start_time - self.now).seconds/self.config.time_horizon.seconds),
        self.navigator.plan(self.pos, self.tasks[self.proccesed].pos).get_distance()/self.area
      ]

      for s in range(4):
        start = self.now + s*self.config.time_slot
        stop = self.now + (s+1)*self.config.time_slot
        for i,j in enumerate(self.jobs):
          if j.start_time >= start and j.start_time < stop or j.deadline > start and j.deadline <= stop or j.start_time < start and j.deadline > stop:
            self.state[4+s*3] += j.priority
            self.state[6+s*3] += 1
        for i,j in enumerate(self.out.scheduled):
          if j.start >= start and j.start < stop or j.stop > start and j.stop <= stop or j.start < start and j.stop > stop:
            self.state[5+s*3] += j.priority

      done = False
      reward = self.profit
      status = "WORK"

    return self.state, reward, done, {"status": status, "steps": self.steps, "fname": self.fname}



  # def step(self, action):
  #   new_state = np.zeros_like(self.state)
  #   done = False
  #   reward = 0

  #   # old behaviour - fixed penalty for changing the task
  #   # if (action != self.selected) and (self.selected != -1):
  #   #   for i in range(self.penalty):
  #   #     new_state = self.do_step(-1)

  #   # new behaviour - calculating the actual cost (time) to travel to a new task
  #   # implemented inside the `do_step` method

  #   switch_penalty = False
  #   if (action != self.selected) and (self.selected != -1):
  #       switch_penalty = True

  #   self.selected = action

  #   status = "WORK"
  #   # big penalty for allowing a task to die or working too long
  #   if not self.is_alive() or self.steps >= self.max_steps:
  #     done = True
  #     reward = -self.config.penalty_dead
  #     status = "DEAD" if not self.is_alive() else "TIME"
  #   else:
  #     # penalty for choosing non-existing or finished task
  #     if self.tasks[action].do_estimate() <= 0:
  #       reward = -self.config.penalty_wrong_task

  #     new_state = self.do_step(action)

  #     # bonus reward for finishing all tasks
  #     if np.sum(new_state, axis=(0,1))[0] == 0:
  #       done = True
  #       status = "DONE"
  #       reward = self.config.reward_finish_all

  #     # reward for finishing single task
  #     if self.tasks[action].do_estimate() <= 0 and reward == 0:
  #       reward = self.config.reward_finish_task

  #     # bonus for selecting actual task
  #     if reward == 0:
  #       reward = self.config.reward_existing_task

  #     reward = reward + np.sum(self.state[:,:,0] - new_state[:,:,0])

  #     if switch_penalty:
  #       reward = reward - self.config.penalty_switch
    
  #   # penalty for switching task

  #   #reward = 0.001 * reward
  #   self.state = new_state
  #   return self.state, reward, done, {"status": status, "steps": self.steps, "fname": self.fname}