import numpy as np
import random
import sys
# sys.path.insert(0, '../../../dqn')
# from tasks import Task
from linear_path_ROS_planner import ROSNavigation
from datetime import datetime, timedelta

class Task:
    id_counter = 0
    def __init__(self):
        self.id = str(Task.id_counter)
        Task.id_counter += 1
        self.age = 0
        self.pos = np.array([0, 0])

    def wait(self, dt):
        self.age = self.age + dt
        self.do_wait(dt)

    def work(self, dt):
        self.age = self.age + dt
        self.do_work(dt)

    def getID(self):
        return self.id

    def getUUID(self):
        raise NotImplementedError()

    def getPriority(self):
        raise NotImplementedError()

    def getDeadline(self):
        raise NotImplementedError()

    def getBurst(self):
        raise NotImplementedError()

    def dist(self, pos):
        raise NotImplementedError()

    def updatePos(self, pos):
        raise NotImplementedError()

    def do_estimate(self):
        raise NotImplementedError()

    def do_wait(self, dt):
        raise NotImplementedError()

    def do_work(self, dt):
        raise NotImplementedError()

    def is_alive(self, now):
        raise NotImplementedError()

# Transport z punkt A do B
class Transport(Task):
    navigator = ROSNavigation()
    uuid_counter = 0
    def __init__(self, deadline, pt1, pt2, spd):
        super().__init__()
        self.uuid = 'transport_' + str(Transport.uuid_counter)
        Transport.uuid_counter+= 1
        self.priority = 0
        self.deadline = deadline
        self.pos = np.array(pt1)
        self.goal = np.array(pt2)
        self.spd = spd
        self.path = Transport.navigator.plan(self.pos, self.goal)

    def getUUID(self):
        return self.uuid

    def getPriority(self):
        return self.priority

    def getDeadline(self):
        return self.deadline

    def getBurst(self):
        return timedelta(seconds = self.path.get_distance()/self.spd)

    def dist(self, pos):
        return np.linalg.norm(pos - self.pos)

    def updatePos(self, pos):
        return self.pos

    def do_estimate(self):
        return self.path.get_distance()

    def do_wait(self, dt):
        pass

    def do_work(self, dt):
        self.path.step(self.spd, dt)
        self.pos = self.path.pos

    def is_alive(self, now):
        return True

    def __str__(self):
        dst = self.do_estimate()
        return f'D | dst: {dst:.2f} m | spd: {self.spd:.2f} m/s'

    __repr__ = __str__
    
    def serialize(self):
      return f"{self.goal[0]}|{self.goal[1]}"

# Upadek w punkcie A
class Fall(Task):
    uuid_counter = 0
    def __init__(self, deadline, pt, urgency):
        super().__init__()
        self.uuid = 'fall_' + str(Fall.uuid_counter)
        Fall.uuid_counter+= 1
        self.priority = 1
        self.deadline = deadline
        self.pos = np.array(pt)
        self.urgency = urgency

    def getUUID(self):
        return self.uuid

    def getPriority(self):
        return self.priority

    def getDeadline(self):
        return self.deadline

    def getBurst(self):
        return timedelta(seconds=self.urgency)
    
    def dist(self, pos):
        return np.linalg.norm(pos - self.pos)

    def updatePos(self, pos):
        return self.pos

    def do_estimate(self):
        return self.urgency

    def do_wait(self, dt):
        pass

    def do_work(self, dt):
        self.urgency = max(self.urgency - dt, 0)

    def is_alive(self, now):
        return now < deadline + timedelta(minutes=15)

    def __str__(self):
        return f'F | urg: {self.urgency:.0f}'

    __repr__ = __str__
    
    def serialize(self):
      return f""


def TransportGenerator(now, time_horizon):
    x_min = 1
    x_max = 10
    y_min = 1
    y_max = 10
    x1 = x_min + random.random() * (x_max - x_min)
    x2 = x_min + random.random() * (x_max - x_min)
    y1 = y_min + random.random() * (y_max - y_min)
    y2 = y_min + random.random() * (y_max - y_min)
    spd_min = 0.1
    spd_max = 1.0
    spd = spd_min + random.random() * (spd_max - spd_min)
    deadline = now + random.random() * time_horizon
    return Transport(deadline, [x1, y1], [x2, y2], spd)

def FallGenerator(now, time_horizon):
    x_min = 0
    x_max = 10
    y_min = 0
    y_max = 10
    x1 = x_min + random.random() * (x_max - x_min)
    y1 = y_min + random.random() * (y_max - y_min)
    urg_min = 60
    urg_max = 600
    urg = urg_min + random.random() * (urg_max - urg_min)
    deadline = now + random.random() * time_horizon
    return Fall(deadline, [x1, y1], urg)

class TaskConfig(object):
    def __init__(self, task_desc, count, now, time_horizon, seed = -1):
        self.types = len(task_desc)
        self.count = count
        self.task_desc = task_desc
        self.now = now
        self.time_horizon = time_horizon
        if seed >= 0:
            self.fix_random = True
            self.seed = seed
        else:
            self.fix_random = False
            self.seed = -1

        # self.task_prob = task_prob

    def generate(self):
        if self.fix_random:
          random.seed(self.seed)
        else:
          random.seed()
          seed = random.randint(0, 10000)
          random.seed(seed)
          self.seed = seed
          
        tasks = []
        for i,t in enumerate(self.task_desc):
          for i in range(self.count):
            task = t(self.now, self.time_horizon)
            tasks.append(task)

        return tasks