# Smit Sim

## Instalation

1. Install appropriate libraries.
- Install the full version of ROS Melodic by following the instructions on their site. For native installation on Ubuntu 18, see [http://wiki.ros.org/melodic/Installation/Ubuntu](http://wiki.ros.org/melodic/Installation/Ubuntu).
- Install required Python3 libraries using pip (we recommend using Python version 3.7.5).
```
pip3 install -r requirements.txt
```

2. Create workspace.
```
mkdir -p smit_ws/src
cd smit_ws/src/
```
3. Clone ROS packages into the workspace. You need to download all three of them for the software to work.
- smit_sim (this package).
```
git clone https://github.com/RCPRG-ros-pkg/Smit-Sim.git
```
- [tasker](https://github.com/RCPRG-ros-pkg/tasker/tree/smit-reqTab) on smit-reqTab branch.
```
git clone -b smit-reqTab https://github.com/RCPRG-ros-pkg/tasker.git
```
- [tasker_msgs](https://github.com/RCPRG-ros-pkg/tasker_msgs/tree/smit) on smit branch
```
git clone -b smit https://github.com/RCPRG-ros-pkg/tasker_msgs.git
```
4. Build the workspace.
```
cd ../..
catkin build
```

## Important files
1. scripts/random_map_server.py - runs the environment - map with obstacles and pedestrians.
2. scripts/global_planner/my_tasks.py - tasks used in our system.
3. scripts/global_planner/my_system.py - scenario that runs tasks.
4. scripts/global_planner/my_agents.py - agents that decide which task to perform.
5. scripts/global_planner/my_eval_functions.py - evaluation functions for assessing agents' work.
6. test_map - default environment configuration.

## Running the environment and utilising the local planner
The system utilises the ROS framework using Python3 and was tested on Ubuntu 18.04.

### Running

1. Build your workspace, including this package, using ROS (catkin build) - see last step of **Installation**.
2. In first console (starting from ROS workspace) run the local planner. Running this command before executing the map script also starts roscore.
```
source devel/setup.bash
roslaunch smit_sim tasks_execution.launch
```
3. In second console (starting from ROS workspace) run the map server. This script can be run with various arguments that alter the map's outcome. These are not ROS arguments, but are implemented using the argparse library instead. See the bottom of the script's contents for the argument list.
```
source devel/setup.bash
rosrun smit_sim random_map_server.py
```
4. (Optional) Load previously created map by sending its filename via a ROS service called /load_config. Service type is FileOperation (included in this package). You can do it with rqt or by console command (example below). The config file directory should be passed in regard to the random_map_server.py file. The sample config file is present in this package under the name 'test_map'.
```
source devel/setup.bash
rosservice call /load_config "filename: 'config_file_directory/config_file_name'"
```
5. (Optional) Run RViz in a separate console to see the map with objects on it. The sample configuration is in this package under the name 'smit_new.rviz'.
```
source devel/setup.bash
rosrun rviz rviz
```

### Planning route

To get a route planned according to the used map, you can call service /planner/make_plan of type MakeNavPlan (from the navfn package). Alternatively, you can utilise the class ROSNavigation from this package to get an object of class LinearPath. You can run the LinearPath.step(robot_speed, move_duration_in_secs) function to move through the path with constant speed for a set amount of time.

### Adding pedestrians

You can add pedestrians to the map by passing an appropriate argument (e.g. --num_of_pedestrians 3).

Alternatively, you can use /add_pedestrian service of type AddPedestrian to add pedestrians to the map. It has the following components:
1. velocity - float64 - pedestrian velocity during move
2. path - std_msgs/Float64MultiArray - list of points from start to goal, if empty - generated randomly
3. full_path - bool - informs if the path is fully planned or only consists of start and goal points
4. behavior - int8 - pedestrian behaviour, 1 - go around in circles, 2 - plan a new random path after completing the previous one, 3 - disappear after path completion, 4 - plan a new random path that starts in a stop place after of previous one

## Running the scenario for the robot performing tasks
The system utilises the ROS framework using Python3 and was tested on Ubuntu 18.04.

1. Perform steps 1-3 from the **Running and utilizing random_map_server with local planner** - **Running** section above.
2. In the third console, run the test_planner.py script (can be found in the scripts/global_planner directory). Currently, this script always loads the 'test_map' map configuration, which is located in this package.
```
source devel/setup.bash
rosrun smit_sim test_planner.py _agent_type:=distance _ratio:=1.0
```
The script can be configured using ROS parameters passed by console. For example, passing a day parameter will determine the random seed for task generation. Example for day 1 below.
```
rosrun smit_sim test_planner.py _day:=1
```
The script uses the Simple agent by default. One can change the agent type using the parameters. Examples below. Most agent types also require additional configuration parameters. 'ratio' and 'hesitance' should be a float number between 0 and 1, while 'dqn_path' should be a path to the network's directory. Examples are presented below.
```
rosrun smit_sim test_planner.py _agent_type:=distance _ratio:=0.5
rosrun smit_sim test_planner.py _agent_type:=simple _hesitance:=0.5
rosrun smit_sim test_planner.py _agent_type:=simple2 _hesitance:=0.5
rosrun smit_sim test_planner.py _agent_type:=scheduler
rosrun smit_sim test_planner.py _agent_type:=dqn dqn_path:=<path_to_network>
```

## Training a DQNAgent
The system utilises the ROS framework using Python3 and was tested on Ubuntu 18.04.

1. Perform steps 1-3 from the **Running and utilizing random_map_server with local planner** - **Running** section above.
2. In the third console, run the train_dqnagent.py script (can be found in the scripts/global_planner directory). Currently, this script always loads the 'test_map' map configuration found in this package. This script trains the DQNAgent, whose code can be found in the scripts/global_planner/my_agents.py file. It uses the DQNEval reward function from scripts/global_planner/my_eval_functions.py.
```
source devel/setup.bash
rosrun smit_sim train_dqnagent.py
```

### DQN training parameters
The training parameters placed in this repository are meant as an example. The user can freely change any of their values to adapt to the current problem by modifying the parameters of the created object from the DQNConfig class. An example of training parameter modification can be found at the bottom of the previously mentioned training script (scripts/global_planner/train_dqnagent.py) or in the image below.

<img width="1000" height="271" alt="obraz" src="https://github.com/user-attachments/assets/3bd02df0-1f73-4ea8-9ab3-d4432474a623" />

### DQN network structure
The user may also freely modify the DQN network structure. This can be achieved by modifying the build_model() function of the DQNAgent class, located in scripts/global_planner/my_agents.py.

<img width="1000" height="179" alt="obraz" src="https://github.com/user-attachments/assets/10aaa104-be97-42cf-8684-e0e013231e55" />

## Modifying/creating a new evaluation function
The above repository contains several evaluation functions. These can be found within the scripts/global_planner/my_eval_functions.py folder and can be easily modified. For example, in order to change the reward for completing a job within a DQNEval evaluation function, one can change the appropriate class property - reward_job_complete.

In order to create a new evaluation function, two new classes must be created: one inheriting from the EvalResult and one inheriting from the EvalFunction. The first class should contain properties corresponding to any information that the system can receive from the newly implemented evaluation function. An object of this class will be returned to the system after every evaluation. The second class should contain the actual evaluation calculations - they must be placed within the necessary calculate_results() function. This function must create, fill and return an instance of the newly created result type.

## Docker
For easy use and a reproducible setup, we provide a Docker image that bundles ROS Melodic, Python 3.7, and all required dependencies. It supports GUI tools (RViz, rqt, Gazebo) via X11 and uses host networking for ROS out of the box. Build and run with the commands below.

### Building Docker image

```bash
docker build -f Dockerfile -t smit-sim . --no-cache
```

### Running (with X11 display)

```bash
xhost +local:docker

docker run -it --name SMIT-SIM \
  --net=host \
  -e DISPLAY=$DISPLAY -e QT_X11_NO_MITSHM=1 \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  smit-sim
```

You can add `--gpus all` for NVIDIA acceleration.


### Usage
You can connect new sessions to this container with:

```bash
docker exec -it SMIT-SIM bash
```

You can stop the container using:

```bash
docker stop SMIT-SIM
```

You can start a stopped container with:

```bash
docker start SMIT-SIM
```

## Introduction video (click on thumbnail to watch)
[![Watch here](https://i.vimeocdn.com/video/2063470934-cbed1eae28af31789dd5d05c1a1d38f2e99348ee35d19eb959e203961376526b-d_640?region=us)](https://vimeo.com/manage/videos/1122196556)

## Example hardware configurations
The above system was successfully run at the following hardware configurations:
- CPU: Intel(R) Core(TM) i7-4510U CPU @ 2.00GHz, RAM: 16Gb, GPU: Intel® HD Graphics 4400 (HSW GT2)
- CPU: AMD Ryzen 5 2600X Six-Core Processor, RAM: 32Gb, GPU: NVIDIA Corporation GP107GL [Quadro P400]
- CPU: 11th Gen Intel(R) Core(TM) i5-1135G7 CPU @ 2.40GHz, RAM: 16Gb, GPU: None
- CPU: 12th Gen Intel(R) Core(TM) i9-12900K, RAM: 32Gb, GPU: NVIDIA GeForce RTX 3080 Ti
