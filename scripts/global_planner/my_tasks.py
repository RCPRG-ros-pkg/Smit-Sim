import numpy as np
import random
import sys
from smit_linear_path.linear_path_ROS_planner import ROSNavigation
from datetime import datetime, timedelta
import time
from time import sleep
import rospy
from smit_sim.srv import GetObjectPose, RemoveObject, AddObject
from geometry_msgs.msg import Pose, Point, Quaternion

class Task:
    id_counter = 0
    def __init__(self):
        self.id = str(Task.id_counter)
        Task.id_counter += 1
        self.age = 0
        self.pos = np.array([0, 0])
        self.preemptive = True
        self.estimated_duration = None
        self.distance_from_robot = 0
        self.calltime = None

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

    def setDeadline(self):
        raise NotImplementedError()

    def getBurst(self):
        raise NotImplementedError()

    def setBurst(self):
        raise NotImplementedError()

    def dist(self, pos):
        raise NotImplementedError()

    def updatePos(self):
        raise NotImplementedError()

    def do_estimate(self):
        raise NotImplementedError()

    def do_wait(self, dt):
        raise NotImplementedError()

    def do_work(self, dt):
        raise NotImplementedError()

    def is_alive(self, now):
        raise NotImplementedError()

    def getDeathTime(self):
        raise NotImplementedError()

    def setCalltime(self, new_calltime):
        self.calltime = new_calltime

class Empty(Task):
    uuid_counter = 0
    def __init__(self, deadline, priority = 0):
        super().__init__()
        self.uuid = 'transport_' + str(Empty.uuid_counter)
        Empty.uuid_counter+= 1
        self.priority = priority
        self.deadline = deadline

    def getUUID(self):
        return self.uuid

    def getPriority(self):
        return self.priority

    def getDeadline(self):
        return self.deadline


# Transport z punkt A do B
class Transport(Task):
    navigator = ROSNavigation()
    uuid_counter = 0
    def __init__(self, deadline, calltime, pt1, pt2, spd):
        super().__init__()
        self.uuid = 'transport_' + str(Transport.uuid_counter)
        Transport.uuid_counter+= 1
        self.priority = random.choice([1, 2, 3])
        self.deadline = deadline
        self.calltime = calltime
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

    def setDeadline(self, new_deadline):
        self.deadline = new_deadline

    def getBurst(self):
        return timedelta(seconds = self.path.get_distance()/self.spd)

    def setBurst(self, new_burst):
        self.spd = self.path.get_distance()/new_burst.seconds

    def dist(self, pos):
        return np.linalg.norm(pos - self.pos)

    def updatePos(self):
        if (self.pos != self.path.pos).any() or (self.goal != self.path.points[-1]).any():
            self.path = Transport.navigator.plan(self.pos, self.goal)

    def do_estimate(self):
        return self.path.get_distance()

    def do_wait(self, dt):
        pass

    def do_work(self, dt):
        self.path.step(self.spd, dt)
        self.pos = self.path.pos

    def is_alive(self, now):
        return True

    def getDeathTime(self):
        return 0

    def __str__(self):
        dst = self.do_estimate()
        return f'{self.uuid} | dst: {dst:.2f} m | spd: {self.spd:.2f} m/s'

    __repr__ = __str__
    
    def serialize(self):
      return f"{self.goal[0]}|{self.goal[1]}"

# Upadek w punkcie A
class Fall(Task):
    uuid_counter = 0
    def __init__(self, deadline, calltime, pt, urgency):
        super().__init__()
        self.uuid = 'fall_' + str(Fall.uuid_counter)
        Fall.uuid_counter+= 1
        self.priority = 4
        self.deadline = deadline
        self.calltime = calltime
        self.pos = np.array(pt)
        self.urgency = urgency
        self.preemptive = False

    def getUUID(self):
        return self.uuid

    def getPriority(self):
        return self.priority

    def getDeadline(self):
        return self.deadline

    def setDeadline(self, new_deadline):
        self.deadline = new_deadline

    def getBurst(self):
        return timedelta(seconds=self.urgency)

    def setBurst(self, new_burst):
        self.urgency = new_burst.seconds
    
    def dist(self, pos):
        return np.linalg.norm(pos - self.pos)

    def updatePos(self):
        pass

    def do_estimate(self):
        return self.urgency

    def do_wait(self, dt):
        pass

    def do_work(self, dt):
        self.urgency = max(self.urgency - dt, 0)

    def is_alive(self, now):
        if self.urgency:
            return now < self.deadline + timedelta(minutes=15)
        else:
            return True

    def getDeathTime(self):
        return self.deadline + timedelta(minutes=15)

    def __str__(self):
        return f'{self.uuid} | urg: {self.urgency:.0f}'

    __repr__ = __str__
    
    def serialize(self):
      return f""

class Pick(Task):
    uuid_counter = 0
    def __init__(self, deadline, calltime, duration, object_id, spawn_zones, forbidden_zones):
        super().__init__()
        self.uuid = 'pick_' + str(Pick.uuid_counter)
        Pick.uuid_counter+= 1
        self.priority = 0
        self.deadline = deadline
        self.calltime = calltime
        self.pos = None
        self.object_pos = None
        self.duration = duration
        self.object_id = object_id
        self.spawn_zones = spawn_zones
        self.forbidden_zones = forbidden_zones
        # rospy.wait_for_service('/get_object_pose')
        self.obj_client = rospy.ServiceProxy('/get_object_pose', GetObjectPose)
        self.preemptive = False
        self.generate_position()

    def generate_position(self):
        resp = self.obj_client(self.object_id)
        if not resp.success:
            return
        new_pos = np.array([resp.pose.position.x, resp.pose.position.y])
        if self.pos is None or (self.object_pos != new_pos).any():
            self.object_pos = new_pos
            self.pos = None
            available_positions = [
                self.object_pos + [1, 0],
                self.object_pos + [1, 1],
                self.object_pos + [0, 1],
                self.object_pos + [-1, 1],
                self.object_pos + [-1, 0],
                self.object_pos + [-1, -1],
                self.object_pos + [0, -1],
                self.object_pos + [1, -1],
            ]
            for point in available_positions:
                x1 = point[0]
                y1 = point[1]
                for zone in self.spawn_zones:
                    if x1 >= zone[0][0] and x1 <= zone[0][1] and y1 >= zone[1][0] and y1 <= zone[1][1]:
                        self.pos = point
                        for fzone in self.forbidden_zones:
                            if x1 >= fzone[0][0] and x1 <= fzone[0][1] and y1 >= fzone[1][0] and y1 <= fzone[1][1]:
                                self.pos = None
                                break
                        if not(self.pos is None):
                            return

    def getUUID(self):
        return self.uuid

    def getPriority(self):
        return self.priority

    def getDeadline(self):
        return self.deadline

    def setDeadline(self, new_deadline):
        self.deadline = new_deadline

    def getBurst(self):
        return timedelta(seconds=self.duration)

    def setBurst(self, new_burst):
        self.duration = new_burst.seconds
    
    def dist(self, pos):
        return np.linalg.norm(pos - self.pos)

    def updatePos(self):
        self.generate_position()

    def do_estimate(self):
        return self.duration

    def do_wait(self, dt):
        pass

    def do_work(self, dt):
        self.duration = max(self.duration - dt, 0)
        # print(f'Pickung up object {self.object_id}, duration left {self.duration}')
        if self.duration == 0:
            client = rospy.ServiceProxy('/remove_object', RemoveObject)
            client(self.object_id)
            # print(f'Removing object {self.object_id}')

    def is_alive(self, now):
        return True

    def getDeathTime(self):
        return 0

    def __str__(self):
        return f'{self.uuid} | dur: {self.duration:.0f}'

    __repr__ = __str__
    
    def serialize(self):
      return f""

class Place(Task): #TODO
    uuid_counter = 0
    def __init__(self, deadline, calltime, pt, duration, object_id, spawn_zones, forbidden_zones):
        super().__init__()
        self.uuid = 'place_' + str(Place.uuid_counter)
        Place.uuid_counter+= 1
        self.priority = 0
        self.deadline = deadline
        self.calltime = calltime
        self.pos = None
        self.object_pos = np.array(pt)
        self.duration = duration
        self.object_id = object_id
        self.spawn_zones = spawn_zones
        self.forbidden_zones = forbidden_zones
        self.preemptive = False
        self.generate_position()

    def generate_position(self):
        available_positions = [
            self.object_pos + [1, 0],
            self.object_pos + [1, 1],
            self.object_pos + [0, 1],
            self.object_pos + [-1, 1],
            self.object_pos + [-1, 0],
            self.object_pos + [-1, -1],
            self.object_pos + [0, -1],
            self.object_pos + [1, -1],
        ]
        for point in available_positions:
            x1 = point[0]
            y1 = point[1]
            for zone in self.spawn_zones:
                if x1 >= zone[0][0] and x1 <= zone[0][1] and y1 >= zone[1][0] and y1 <= zone[1][1]:
                    self.pos = point
                    for fzone in self.forbidden_zones:
                        if x1 >= fzone[0][0] and x1 <= fzone[0][1] and y1 >= fzone[1][0] and y1 <= fzone[1][1]:
                            self.pos = None
                            break
                    if not (self.pos is None):
                        return

    def getUUID(self):
        return self.uuid

    def getPriority(self):
        return self.priority

    def getDeadline(self):
        return self.deadline

    def setDeadline(self, new_deadline):
        self.deadline = new_deadline

    def getBurst(self):
        return timedelta(seconds=self.duration)

    def setBurst(self, new_burst):
        self.duration = new_burst.seconds
    
    def dist(self, pos):
        return np.linalg.norm(pos - self.pos)

    def updatePos(self):
        pass

    def do_estimate(self):
        return self.duration

    def do_wait(self, dt):
        pass

    def do_work(self, dt):
        self.duration = max(self.duration - dt, 0)
        # print(f'Placing object {self.object_id}, duration left {self.duration}')
        if self.duration == 0:
            client = rospy.ServiceProxy('/add_object', AddObject)
            client(self.object_id, Pose(Point(self.object_pos[0], self.object_pos[1],0),Quaternion(0, 0, 0, 1)))
            # print(f'Placed object {self.object_id}')

    def is_alive(self, now):
        return True

    def getDeathTime(self):
        return 0

    def __str__(self):
        return f'{self.uuid} | dur: {self.duration:.0f}'

    __repr__ = __str__
    
    def serialize(self):
      return f""


class PickAndPlace(Task):
    uuid_counter = 0
    def __init__(self, task_list):
        super().__init__()
        self.uuid = 'pickandplace_' + str(PickAndPlace.uuid_counter)
        PickAndPlace.uuid_counter+= 1
        self.task_list = task_list
        self.priority = sum([task.priority for task in self.task_list])
        self.deadline = max([task.deadline for task in self.task_list])
        self.calltime = min([task.calltime for task in self.task_list])
        self.pos = task_list[0].pos
        self.goal = task_list[-1].pos
        self.duration = sum([task.getBurst().seconds for task in self.task_list])
        self.preemptive = False

    def getUUID(self):
        return self.uuid

    def getPriority(self):
        return self.priority

    def getDeadline(self):
        return self.deadline

    def setDeadline(self, new_deadline):
        for t in self.task_list:
            if t.deadline == self.deadline:
                t.setDeadline(new_deadline)
                break
        self.deadline = new_deadline

    def getBurst(self):
        self.duration = sum([task.getBurst().seconds + task.getBurst().microseconds/1000000 for task in self.task_list])
        return timedelta(seconds=self.duration)

    def setBurst(self, new_burst):
        self.task_list[0].setBurst(new_burst)
        self.duration = sum([task.getBurst().seconds + task.getBurst().microseconds/1000000 for task in self.task_list])

    def dist(self, pos):
        return np.linalg.norm(pos - self.pos)

    def updatePos(self):
        for i,task in enumerate(self.task_list):
            if isinstance(task, Pick):
                task.updatePos()
            if isinstance(task, Transport) and i > 0:
                task.pos = self.task_list[i-1].pos
                task.updatePos()
        self.pos = self.task_list[0].pos
        self.duration = sum([task.getBurst().seconds + task.getBurst().microseconds/1000000 for task in self.task_list])

    def do_estimate(self):
        self.duration = sum([task.getBurst().seconds + task.getBurst().microseconds/1000000 for task in self.task_list])
        return self.duration

    def do_wait(self, dt):
        pass

    def do_work(self, dt):
        time_left = dt
        while(self.task_list[0].getBurst().seconds + self.task_list[0].getBurst().microseconds/1000000 < time_left and len(self.task_list) > 1):
            time_left -= self.task_list[0].getBurst().seconds + self.task_list[0].getBurst().microseconds/1000000
            self.task_list[0].do_work(dt)
            self.task_list.pop(0)
        self.task_list[0].do_work(time_left)

    def is_alive(self, now):
        return True

    def getDeathTime(self):
        return 0

    def setCalltime(self, new_calltime):
        for t in self.task_list:
            if t.calltime == self.calltime:
                t.setCalltime(new_calltime)
                break
        self.calltime = new_calltime

    def __str__(self):
        return f'{self.uuid} | dur: {self.duration:.0f}'

    __repr__ = __str__
    
    def serialize(self):
      return f""

def TransportGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones):
    # define absolutes
    x_min = min([zone[0][0] for zone in spawn_zones])
    x_max = max([zone[0][1] for zone in spawn_zones])
    y_min = min([zone[1][0] for zone in spawn_zones])
    y_max = max([zone[1][1] for zone in spawn_zones])
    # initialize positions
    x1 = x_min + random.random() * (x_max - x_min)
    y1 = y_min + random.random() * (y_max - y_min)
    x2 = x_min + random.random() * (x_max - x_min)
    y2 = y_min + random.random() * (y_max - y_min)
    # regenerate until proper start positions are found
    while(True):
        in_room = False
        for zone in spawn_zones:
            if x1 >= zone[0][0] and x1 <= zone[0][1] and y1 >= zone[1][0] and y1 <= zone[1][1]:
                in_room = True
                for fzone in forbidden_zones:
                    if x1 >= fzone[0][0] and x1 <= fzone[0][1] and y1 >= fzone[1][0] and y1 <= fzone[1][1]:
                        in_room = False
                        break
                # print(f'{x1} in {zone}')
                break
        # if position is inside a room exit loop
        if in_room:
            break
        # generate new posiitons
        x1 = x_min + random.random() * (x_max - x_min)
        y1 = y_min + random.random() * (y_max - y_min)
    # regenerate until proper stop positions are found
    while(True):
        in_room = False
        for zone in spawn_zones:
            if x2 >= zone[0][0] and x2 <= zone[0][1] and y2 >= zone[1][0] and y2 <= zone[1][1]:
                in_room = True
                for fzone in forbidden_zones:
                    if x2 >= fzone[0][0] and x2 <= fzone[0][1] and y2 >= fzone[1][0] and y2 <= fzone[1][1]:
                        in_room = False
                        break
                # print(f'{x2} in {zone}')
                break
        # if position is inside a room exit loop
        if in_room:
            break
        # generate new posiitons
        x2 = x_min + random.random() * (x_max - x_min)
        y2 = y_min + random.random() * (y_max - y_min)
    spd_min = 0.01
    spd_max = 0.1
    spd = spd_min + random.random() * (spd_max - spd_min)
    deadline = now + random.random() * time_horizon
    calltime = now + time_horizon
    while calltime > deadline - timedelta(seconds = 5):
        calltime = now + random.random() * time_horizon - timedelta(seconds = 5)
    return Transport(deadline, calltime, [x1, y1], [x2, y2], spd)

def FallGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones):
    # define absolutes
    x_min = min([zone[0][0] for zone in spawn_zones])
    x_max = max([zone[0][1] for zone in spawn_zones])
    y_min = min([zone[1][0] for zone in spawn_zones])
    y_max = max([zone[1][1] for zone in spawn_zones])
    # initialize positions
    x1 = x_min + random.random() * (x_max - x_min)
    y1 = y_min + random.random() * (y_max - y_min)
    # regenerate until proper positions are found
    while(True):
        in_room = False
        for zone in spawn_zones:
            if x1 >= zone[0][0] and x1 <= zone[0][1] and y1 >= zone[1][0] and y1 <= zone[1][1]:
                in_room = True
                for fzone in forbidden_zones:
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
    urg_min = 60
    urg_max = 300
    urg = urg_min + random.random() * (urg_max - urg_min)
    deadline = now + random.random() * time_horizon
    calltime = now + time_horizon
    while calltime > deadline - timedelta(seconds = 5):
        calltime = now + random.random() * time_horizon - timedelta(seconds = 5)
    return Fall(deadline, calltime, [x1, y1], urg)

def PickGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones):
    object_id = random.choice(objects)
    urg_min = 60
    urg_max = 300
    duration = urg_min + random.random() * (urg_max - urg_min)
    deadline = now + random.random() * time_horizon
    calltime = now + time_horizon
    while calltime > deadline - timedelta(seconds = 5):
        calltime = now + random.random() * time_horizon - timedelta(seconds = 5)
    return Pick(deadline, calltime, duration, object_id, spawn_zones, forbidden_zones)

def PlaceGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones):
    # define absolutes
    x_min = min([zone[0][0] for zone in object_zones])
    x_max = max([zone[0][1] for zone in object_zones])
    y_min = min([zone[1][0] for zone in object_zones])
    y_max = max([zone[1][1] for zone in object_zones])
    # initialize positions
    x1 = x_min + random.random() * (x_max - x_min)
    y1 = y_min + random.random() * (y_max - y_min)
    # regenerate until proper start positions are found
    while(True):
        in_room = False
        for zone in object_zones:
            if x1 >= zone[0][0] and x1 <= zone[0][1] and y1 >= zone[1][0] and y1 <= zone[1][1]:
                in_room = True
                break
        # if position is inside a room exit loop
        if in_room:
            break
        # generate new posiitons
        x1 = x_min + random.random() * (x_max - x_min)
        y1 = y_min + random.random() * (y_max - y_min)
    object_id = random.choice(objects)
    urg_min = 60
    urg_max = 300
    duration = urg_min + random.random() * (urg_max - urg_min)
    deadline = now + random.random() * time_horizon
    calltime = now + time_horizon
    while calltime > deadline - timedelta(seconds = 5):
        calltime = now + random.random() * time_horizon - timedelta(seconds = 5)
    return Place(deadline, calltime, [x1, y1], duration, object_id, spawn_zones, forbidden_zones)

def PickAndPlaceGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones):
    pick = PickGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones)
    place = PlaceGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones)
    place.object_id = pick.object_id
    transport = TransportGenerator(now, time_horizon, spawn_zones, forbidden_zones, objects, object_zones)
    transport.pos = pick.pos
    transport.goal = place.pos
    transport.updatePos()
    return PickAndPlace([pick, place, transport])

class TaskConfig(object):
    def __init__(self, task_desc, count, now, time_horizon, seed = -1, random_task_count = 0, deadline_variation = 0, burst_variation = 0, randomize_call_time = False, instant_call = False):
        self.types = len(task_desc)
        self.count = count
        self.rcount = random_task_count
        self.task_desc = task_desc
        self.now = now
        self.time_horizon = time_horizon
        if seed >= 0:
            self.fix_random = True
            self.seed = seed
        else:
            self.fix_random = False
            self.seed = -1
        self.b_var = burst_variation
        self.d_var = deadline_variation
        self.random_call = randomize_call_time
        self.instant_call = instant_call

        # self.task_prob = task_prob

    def generate(self, spawn_zones = [((1,9),(1,9))], forbidden_zones = [((0, 0), (0, 0))], objects = [], object_zones = [((0, 0),(0, 0))]):
        Task.id_counter = 0
        if self.fix_random:
          random.seed(self.seed)
        else:
          seed = random.randint(0, 10000)
          random.seed(seed)
          self.seed = seed
          
        tasks = []
        for i,t in enumerate(self.task_desc):
          for i in range(self.count):
            task = t(self.now, self.time_horizon, spawn_zones, forbidden_zones, objects, object_zones)
            print(task.uuid)
            # print(task.pos)
            # print(task.goal)
            # sleep(1)
            tasks.append(task)

        if self.instant_call:
            for t in tasks:
                t.setCalltime(self.now)
        elif self.random_call:
            random.seed(time.time())
            for t in tasks:
                calltime = self.now + self.time_horizon
                while calltime > t.deadline - timedelta(seconds = 5):
                    calltime = self.now + random.random() * self.time_horizon - timedelta(seconds = 5)
                t.setCalltime(calltime)

        if self.d_var:
            random.seed(time.time())
            for t in tasks:
                t.setDeadline(t.getDeadline() + random.uniform(-self.d_var, self.d_var) * t.getBurst())

        if self.b_var:
            random.seed(time.time())
            for t in tasks:
                t.setBurst(timedelta(seconds = t.getBurst().seconds + random.uniform(-self.b_var, self.b_var) * t.getBurst().seconds))

        if self.rcount > 0:
            random.seed(time.time())
            for i,t in enumerate(self.task_desc):
              for i in range(self.rcount):
                task = t(self.now, self.time_horizon, spawn_zones, forbidden_zones, objects, object_zones)
                print(task.uuid)
                tasks.append(task)

        return tasks