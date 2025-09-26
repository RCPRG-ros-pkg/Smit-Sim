FROM osrf/ros:melodic-desktop-full

# --- Basic tools and ROS build dep
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo git wget curl lsb-release ca-certificates gnupg software-properties-common \
    python3 python3-pip python3-dev \
    build-essential \
    python-catkin-tools \
    ros-melodic-navfn \
    ros-melodic-move-base \
    ros-melodic-move-base-msgs \
    ros-melodic-geometry-msgs \
    ros-melodic-nav-msgs \
    ros-melodic-visualization-msgs \
    ros-melodic-tf \
    ros-melodic-global-planner \
    ros-melodic-rviz \
    python-rosdep \
 && rm -rf /var/lib/apt/lists/*

# --- Install Python 3.7 and make it default python3
# Note: base (Ubuntu 18.04) ships python3.6; we add 3.7 from deadsnakes.
RUN add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
        python3.7 python3.7-dev python3.7-distutils \
    && rm -rf /var/lib/apt/lists/*

# Install pip for Python 3.7 specifically and prefer it system-wide
RUN curl -sS https://bootstrap.pypa.io/pip/3.7/get-pip.py -o /tmp/get-pip.py && \
    python3.7 /tmp/get-pip.py "pip==21.3.1" "setuptools<60" wheel && \
    rm -f /tmp/get-pip.py

# Point /usr/bin/python3 to 3.7 (keep 3.6 as a lower-priority alternative)
# Also prefer pip3 from the 3.7 installation (usually /usr/local/bin/pip3)
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.6 10 || true && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.7 20 && \
    update-alternatives --set python3 /usr/bin/python3.7 && \
    if [ -x /usr/local/bin/pip3 ]; then \
        update-alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3 10 || true; \
        update-alternatives --install /usr/bin/pip3 pip3 /usr/local/bin/pip3 20; \
        update-alternatives --set pip3 /usr/local/bin/pip3; \
    fi

# --- rosdep init/update
RUN rosdep init || true && rosdep update

# --- Python3 (now 3.7) pip setup
RUN python3 -m pip install --upgrade "pip==21.3.1" "setuptools<60" wheel

ENV WS=/root/smit_ws
RUN mkdir -p $WS/src
WORKDIR $WS/src

# Smit-Sim (your fork or upstream), plus required deps/branches from README
RUN git clone -b smit-reqTab https://github.com/RCPRG-ros-pkg/tasker.git && \
    git clone -b smit https://github.com/RCPRG-ros-pkg/tasker_msgs.git

# Install smit-sim python requirements
COPY . $WS/src/smit_sim
WORKDIR $WS/src/smit_sim
RUN python3 -m pip install -r requirements.txt

# --- Install system deps via rosdep, then build
WORKDIR $WS
RUN apt-get update && rosdep install --from-paths src --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/* && \
    /bin/bash -lc "source /opt/ros/melodic/setup.bash && catkin build"

# --- Convenience: source on container start
RUN echo "source /opt/ros/melodic/setup.bash && source /root/smit_ws/devel/setup.bash" >> /root/.bashrc

CMD ["/bin/bash"]
