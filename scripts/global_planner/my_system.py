import random
import numpy as np
import sys
import os
from shutil import copyfile
from datetime import datetime, timedelta, date, time
import math as m
sys.path.insert(0, '../')
from my_tasks import Transport, Empty
from linear_path_ROS_planner import ROSNavigation
sys.path.insert(0, '../../../tasker/src/TaskER/')
from RequestTable import RequestTable, ScheduleRules, ScheduleRule, TaskerReqest
import rospy
from smit_matlab_sim.srv import GetRoomsAndDoors, GetFurniture, GetObjects
import tensorflow as tf
from train_estimator import get_estimator_model

class SystemConfig(object):
  def __init__(self):
    self.robot_speed = 0.5
    self.robot_radius = 0.3
    self.time_horizon = timedelta(hours = 1)
    self.start = datetime.combine(date.today(), time(8, 0))
    self.stop = datetime.combine(date.today(), time(20, 0))
    self.time_slot = timedelta(minutes = 5)
    self.dt = timedelta(seconds = 5)
    self.save = False
    self.prefix = ""
    self.day = 1
    self.estimator_path = 'estimator_model/save_20'
    self.predictor_path = 'predictor_model/save_100'
    self.use_estimator = True

class System():
  def __init__(self, task_config, config = SystemConfig()):
    self.config = config
    self.task_config = task_config
    self.tasks = []
    self.now = self.config.start

    if self.config.use_estimator or self.config.save:
      self.estimator = get_estimator_model()
      self.estimator.load_weights(self.config.estimator_path)

    # self.predictor = tf.keras.models.Sequential([
    #   tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(64)),
    #   tf.keras.layers.Dense(36),
    # ])
    # self.predictor.load_weights(self.config.predictor_path)
    
    self.slot_count_horizon = int(self.config.time_horizon/self.config.time_slot)
    self.slot_count_day = int((self.config.stop - self.config.start)/self.config.time_slot)
    self.time_to_horizon = self.slot_count_day/self.slot_count_horizon/(self.config.stop - self.config.start).seconds
    self.time_to_slot = self.slot_count_day/(self.config.stop - self.config.start).seconds
    self.schedule_shape = (3 * self.slot_count_horizon)
    self.schedule = np.zeros(self.schedule_shape)
    self.navigator = ROSNavigation()
    
    rospy.wait_for_service('/get_rooms_and_doors')
    doors_client = rospy.ServiceProxy('/get_rooms_and_doors', GetRoomsAndDoors)
    doors_response = doors_client()
    # print(doors_response)
    self.spawn_zones = [((room.x[0] + self.config.robot_radius, room.x[1] - self.config.robot_radius), (room.y[0] + self.config.robot_radius, room.y[1] - self.config.robot_radius)) for room in doors_response.rooms]
    # print(self.spawn_zones)
    
    rospy.wait_for_service('/get_furniture')
    furn_client = rospy.ServiceProxy('/get_furniture', GetFurniture)
    furn_response = furn_client()
    # print(furn_response)
    self.object_zones = [((room.x[0], room.x[1]), (room.y[0], room.y[1])) for room in furn_response.furniture]
    self.forbidden_spawn_zones = [((room.x[0] - self.config.robot_radius, room.x[1] + self.config.robot_radius), (room.y[0] - self.config.robot_radius, room.y[1] + self.config.robot_radius)) for room in furn_response.furniture]
    # print(self.forbidden_spawn_zones)
    
    rospy.wait_for_service('/get_objects')
    obj_client = rospy.ServiceProxy('/get_objects', GetObjects)
    obj_response = obj_client()
    # print(obj_response)
    self.objects = [o.id for o in obj_response.objects]

    self.reset()

  def close(self):
    if self.config.save:
      self.estimator_file_out.close()
      self.predictor_file_out.close()

  def reset(self):
    print('Resetting...')
    self.now = self.config.start
    self.tasks = self.task_config.generate(self.spawn_zones, self.forbidden_spawn_zones, self.objects, self.object_zones)

    # initial agent position
    # define absolutes
    x_min = min([zone[0][0] for zone in self.spawn_zones])
    x_max = max([zone[0][1] for zone in self.spawn_zones])
    y_min = min([zone[1][0] for zone in self.spawn_zones])
    y_max = max([zone[1][1] for zone in self.spawn_zones])
    # initialize positions
    x1 = x_min + random.random() * (x_max - x_min)
    y1 = y_min + random.random() * (y_max - y_min)
    # regenerate until proper positions are found
    while(True):
        in_room = False
        for zone in self.spawn_zones:
            if x1 >= zone[0][0] and x1 <= zone[0][1] and y1 >= zone[1][0] and y1 <= zone[1][1]:
                in_room = True
                for fzone in self.forbidden_spawn_zones:
                    if x1 >= fzone[0][0] and x1 <= fzone[0][1] and y1 >= fzone[1][0] and y1 <= fzone[1][1]:
                        in_room = False
                        break
                break
        # if position is inside a room exit loop
        if in_room:
            break
        # generate new posiitons
        x1 = x_min + random.random() * (x_max - x_min)
        y1 = y_min + random.random() * (y_max - y_min)
    self.pos = np.array([x1, y1])

    self.current = None
    self.previous = None

    # create save files
    if self.config.save:
      now = datetime.now() # current date and time
      fname = self.config.prefix + now.strftime(f"%Y%m%d_%H%M%S_%f")

      self.fname = 'estimator/timeseries/' + fname + '.csv'
      if not os.path.exists('/'.join(self.fname.split('/')[:-1])):
        os.makedirs('/'.join(self.fname.split('/')[:-1]))
      self.estimator_file_out = open(self.fname, "w")

      self.fname = 'predictor/timeseries/' + fname + '.csv'
      if not os.path.exists('/'.join(self.fname.split('/')[:-1])):
        os.makedirs('/'.join(self.fname.split('/')[:-1]))
      self.predictor_file_out = open(self.fname, "w")

      self.next_save = self.now + self.config.time_slot

    # initialize tasker
    self.rt = RequestTable()
    self.jobIDs = []
    self.jobs = []
    self.out = []
    self.profit = 0
    self.update_jobs()

    self.schedule = np.zeros(self.schedule_shape)
    self.predicted_schedule = np.zeros(self.schedule_shape)
    self.empty_tasks = []
    self.empty_jobs = []

    if self.config.save:
      self.save_schedule()

    print("Reset done")

  def update_jobs(self):
    self.time_eval = (self.now - self.config.start).seconds*self.time_to_horizon
    # update existing job durations
    updated_jobs = False
    if len(self.jobs) > 0 and self.previous != self.current and self.previous != None:
      updated_jobs = True
      for i,job in enumerate(self.jobs):
        t = self.getTaskById(job.id)
        t.updatePos()
        if self.config.use_estimator:
          job.set_burst_time(timedelta(seconds = np.array(self.estimator(np.expand_dims(np.array([
                      self.time_eval,
                      self.config.day,
                      (t.getDeadline() - self.config.start).seconds*self.time_to_horizon,
                      t.pos[0],
                      t.pos[1],
                      t.goal[0] if isinstance(t, Transport) else t.pos[0],
                      t.goal[1] if isinstance(t, Transport) else t.pos[1],
                      self.navigator.plan(self.pos, t.pos).get_distance(),
                      t.getPriority(),
                    ]), axis = 0)))[0,0] * self.config.time_horizon.seconds))
        else:
          burst = t.getBurst() + timedelta(seconds = self.navigator.plan(self.pos, t.pos).get_distance() / self.config.robot_speed)
          job.set_burst_time(burst)
        job.evaluate_rules()
        self.rt.updateRecord(job)
        self.save_estimation(t, job)
    #generate new jobs
    new_jobs = False
    for t in self.tasks:
      if t.getID() in self.jobIDs:
        continue
      elif t.calltime < self.now and t.do_estimate():
        t.updatePos()
        new_jobs = True
        self.jobIDs.append(t.getID())
        sr = ScheduleRules()
        sr.addRule(ScheduleRule(rule_type='at', rule_value=t.getDeadline()))
        job = TaskerReqest(ID=t.getID(),huid=t.getUUID(), plan_args='', req_time=self.now, shdl_rules=sr, priority=t.getPriority())
        if self.config.use_estimator:
          job.set_burst_time(timedelta(seconds = np.array(self.estimator(np.expand_dims(np.array([
                            self.time_eval,
                            self.config.day,
                            (t.getDeadline() - self.config.start).seconds*self.time_to_horizon,
                            t.pos[0],
                            t.pos[1],
                            t.goal[0] if isinstance(t, Transport) else t.pos[0],
                            t.goal[1] if isinstance(t, Transport) else t.pos[1],
                            self.navigator.plan(self.pos, t.pos).get_distance(),
                            t.getPriority(),
                          ]), axis = 0)))[0,0] * self.config.time_horizon.seconds))
        else:
          burst = t.getBurst() + timedelta(seconds = self.navigator.plan(self.pos, t.pos).get_distance() / self.config.robot_speed)
          job.set_burst_time(burst)
        job.evaluate_rules()
        self.rt.addRecord(job)
        self.jobs.append(job)
        self.save_estimation(t, job)
    # update tasker
    if new_jobs or updated_jobs:
      self.out, self.profit = self.rt.schedule_with_priority()
    if len(self.jobs) == 0 and self.previous != self.current:
      self.out, self.profit = self.rt.schedule_with_priority()

  def getTaskById(self, task_id):
    return [task for task in self.tasks if task.id == task_id][0]

  def getJobById(self, job_id):
    return [job for job in self.jobs if job.id == job_id][0]

  def removeJobById(self, job_id):
    self.rt.removeRecord_by_id(self.current)
    for i,job in enumerate(self.jobs):
      if job.id == job_id:
        break
    self.jobs.pop(i)

  def step(self):
    # print(self.jobIDs)
    # select action
    self.previous = self.current
    current_task = None
    current_job = None
    if len(self.jobs) > 0:
      if self.current or self.current == 0:
        current_task = self.getTaskById(self.current)
        current_job = self.getJobById(self.current)
        if not current_task.preemptive or current_job.deadline > self.now:
          pass
        else:
          self.current = None
          current_job = None
      if self.current == None:
        for job in self.out.scheduled:
          if job.start <= self.now + self.config.dt and job.stop > self.now:
            self.current = job.jobID
            current_job = self.getJobById(self.current)
            current_task = self.getTaskById(self.current)
            print(f'Current: {self.current}')
            break

    # perform action
    if not(current_job is None):
      time_left = self.config.dt.seconds

      # do the actual travel to the action spot if distanse from the agent is greater than threshold
      if current_task.dist(self.pos) > 0.1:
        path = self.navigator.plan(self.pos, current_task.pos)
        [self.pos, time_left] = path.step(self.config.robot_speed, time_left)

      # work on a task
      if time_left > 0:
        current_task.do_work(time_left)
        self.pos = current_task.pos

      # if task is done remove it from TaskER and job list
      if not current_task.do_estimate():
        print('Worked on job ' + str(self.current) + ': ' + str(current_task.do_estimate()))
        print('Job ' + str(self.current) + ' complete')
        self.removeJobById(self.current)
        self.current = None
      else:
        print('Worked on job ' + str(self.current) + ': ' + str(current_task.do_estimate()))

    self.now = self.now + self.config.dt

  def generate_schedule(self):
    self.schedule = np.zeros(self.schedule_shape)
    for s in range(self.slot_count_horizon):
      start = self.now + s*self.config.time_slot
      stop = self.now + (s+1)*self.config.time_slot
      for i,j in enumerate(self.jobs):
        if j.start_time >= start and j.start_time < stop or j.deadline > start and j.deadline <= stop or j.start_time < start and j.deadline > stop:
          self.schedule[s*3] += j.priority
          self.schedule[2+s*3] += 1
      for i,j in enumerate(self.out.scheduled):
        if j.start >= start and j.start < stop or j.stop > start and j.stop <= stop or j.start < start and j.stop > stop:
          self.schedule[1+s*3] += self.rt.get_request(j.jobID).priority

  # def predict_schedule(self):
  #   if len(self.empty_jobs):
  #     for j in self.empty_jobs:
  #       rt.removeRecord_by_id(j.jobID)

  #   self.empty_tasks = []
  #   self.empty_jobs = []
  #   self.predicted_schedule = np.array(self.predictor(np.expand_dims(np.expand_dims(np.concatenate((np.array([(self.now - self.config.start).seconds*self.time_to_horizon, self.config.day]), self.schedule)), axis = 0), axis = 0))[0])

  #   for s in range(self.slot_count_horizon - 1):
  #     task_diff = round(self.predicted_schedule[s*3] - self.schedule[(s+1)*3])
  #     if task_diff > 0:
  #       print(f'Adding {task_diff} empty_tasks')
  #       task_priorities = round((self.predicted_schedule[s*3 + 2] - self.schedule[(s+1)*3 + 2])/task_diff)
  #       for i in range(task_diff):
  #         t = Empty(self.now + (s+1)*self.config.time_horizon, task_priorities)
  #         self.empty_tasks.append(t)
  #         sr = ScheduleRules()
  #         sr.addRule(ScheduleRule(rule_type='at', rule_value=t.getDeadline()))
  #         job = TaskerReqest(ID=t.getID(),huid=t.getUUID(), plan_args='', req_time=self.now, shdl_rules=sr, priority=t.getPriority())
  #         job.set_burst_time(self.config.time_slot)
  #         job.evaluate_rules()
  #         self.rt.addRecord(job)
  #         self.empty_jobs.append(job)

  #   if len(self.empty_jobs):
  #     self.out, self.profit = self.rt.schedule_with_priority()

  def save_estimation(self, task, job):
    if self.config.save:
      self.estimator_file_out.write(':'.join([
          str((self.now - self.config.start).seconds*self.time_to_horizon),
          str(self.config.day),
          str((task.deadline - self.config.start).seconds*self.time_to_horizon),
          str(task.pos[0]),
          str(task.pos[1]),
          str(task.goal[0] if isinstance(task, Transport) else task.pos[0]),
          str(task.goal[1] if isinstance(task, Transport) else task.pos[1]),
          str(self.navigator.plan(self.pos, task.pos).get_distance()),
          str(job.priority),
          str(job.burst_time.seconds*self.time_to_horizon),
        ]) + '\n')

  def save_schedule(self):    
    if self.config.save:
      if len(self.jobs):
        self.generate_schedule()
      self.predictor_file_out.write(str((self.now - self.config.start).seconds*self.time_to_horizon) + ':' + str(self.config.day) + ':' + ':'.join([str(s) for s in self.schedule]) + '\n')

  def save(self):
    if self.config.save:
      if self.now >= self.next_save:
        self.next_save += self.config.time_slot
        self.save_schedule()
        for i,job in enumerate(self.jobs):
          t = self.tasks[int(self.jobIDs[i])]
          self.save_estimation(t, job)

  def run_env(self):
    while(self.now < self.config.stop):
      print("Stepping from " + str(self.now) + " to " + str(self.now + self.config.dt))
      # self.predict_schedule()
      self.step()
      self.update_jobs()
      self.save()

    print(f'Scheduled: {len(self.out.scheduled)}, Rejected: {len(self.out.rejected)}')
    self.close()
