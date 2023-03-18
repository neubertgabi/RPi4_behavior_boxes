#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# python3: headfixed_task.py
"""
author: tian qiu
date: 2023-01-26
name: self_admin_Task.py
goal: self administration task adpated via Mitch's instruction
description:
    an updated test version of self_admin_Task.py

"""
import importlib
from transitions import Machine
from transitions import State
from transitions.extensions.states import add_state_features, Timeout
import pysistence, collections
from icecream import ic
import logging
import time
from datetime import datetime
import os
from gpiozero import PWMLED, LED, Button
from colorama import Fore, Style
import logging.config
from time import sleep
import random
import threading
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.figure as fg
import numpy as np

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": True,
    }
)
# all modules above this line will have logging disabled

import behavbox


# adding timing capability to the state machine
@add_state_features(Timeout)
class TimedStateMachine(Machine):
    pass


class SelfAdminTask(object):
    # Define states. States where the animals is waited to make their decision

    def __init__(self, **kwargs):  # name and session_info should be provided as kwargs

        # if no name or session, make fake ones (for testing purposes)
        if kwargs.get("name", None) is None:
            self.name = "name"
            print(
                Fore.RED
                + Style.BRIGHT
                + "Warning: no name supplied; making fake one"
                + Style.RESET_ALL
            )
        else:
            self.name = kwargs.get("name", None)

        if kwargs.get("session_info", None) is None:
            print(
                Fore.RED
                + Style.BRIGHT
                + "Warning: no session_info supplied; making fake one"
                + Style.RESET_ALL
            )
            from fake_session_info import fake_session_info

            self.session_info = fake_session_info
        else:
            self.session_info = kwargs.get("session_info", None)
        ic(self.session_info)

        # initialize the state machine
        self.states = [
            Timeout(name='standby',
                  on_enter=["enter_standby"],
                  on_exit=["exit_standby"],
                  timeout=self.session_info['standby_timeout'],  #ADD STANDBY TIMEOUT TO SESSION_INFO = 5min
                  on_timeout=['switch_to_reward_available'])
            Timeout(name='reward_available',
                    on_enter=["enter_reward_available"],
                    on_exit=["exit_reward_available"],
                    timeout=self.session_info["reward_timeout"], #5 min; In self_admin_task program, this is just a restart signal that counts the trials doesn't really do anything. So I can update this to switch to standby
                    on_timeout=["switch_to_standby"])]
        
        self.transitions = [
            ['switch_to_reward_available', 'standby', 'reward_available'],  # format: ['trigger', 'origin', 'destination']
            ['switch_to_standby', 'reward_available', 'standby']]

        self.machine = TimedStateMachine(
            model=self,
            states=self.states,
            transitions=self.transitions,
            initial='standby'  #STARTS IN STANDBY MODE
        )
        self.trial_running = False

        # trial statistics
        self.innocent = True
        self.trial_number = 0
        self.error_count = 0
        self.error_list = []
        self.error_repeat = False
        self.lever_pressed_time = 0.0
        self.lever_press_interval = self.session_info["lever_press_interval"]
        # self.reward_time_start = None # for reward_available state time keeping purpose
        self.reward_time = 10 # sec. could be incorporate into the session_info; available time for reward
        self.reward_times_up = False
        self.reward_pump = self.session_info["reward_pump"]
        self.reward_size = self.session_info["reward_size"]

        self.active_press = 0
        self.inactive_press = 0
        self.timeline_active_press = []
        self.active_press_count_list = []
        self.timeline_inactive_press = []
        self.inactive_press_count_list = []

        self.left_poke_count = 0
        self.right_poke_count = 0
        self.timeline_left_poke = []
        self.left_poke_count_list = []
        self.timeline_right_poke = []
        self.right_poke_count_list = []
        self.event_name = ""
        # initialize behavior box
        self.box = behavbox.BehavBox(self.session_info)
        self.pump = self.box.pump
        self.treadmill = self.box.treadmill

        # self.distance_initiation = self.session_info['treadmill_setup']['distance_initiation']
        # self.distance_cue = self.session_info['treadmill_setup']['distance_cue']
        # self.distance_buffer = None
        # self.distance_diff = 0

        # for refining the lick detection
        self.lick_count = 0
        self.side_mice_buffer = None
        self.LED_blink = False
        try:
            self.lick_threshold = self.session_info["lick_threshold"]
        except:
            print("No lick_threshold defined in session_info. Therefore, default defined as 2 \n")
            self.lick_threshold = 1

        # session_statistics
        self.total_reward = 0

    ########################################################################
    # functions called when state transitions occur
    ########################################################################
    def run(self):
        if self.box.event_list:
            self.event_name = self.box.event_list.popleft()
        else:
            self.event_name = ""
        if self.state == "standby":
            if self.event_name == "reserved_rx1_pressed":
                print('neutral_context_active_press')
        elif self.state == "reward_available":
            if self.event_name == "reserved_rx1_pressed": #if there's a lever press during state reward_available
                print('reward_context_active_press')
                lever_pressed_time_temp = time.time() #assign the lever_pressed_time_temp to the current time
                lever_pressed_dt = lever_pressed_time_temp - self.lever_pressed_time #lever_pressed_dt subtracts the current lever press time from the previous lever press time
                if lever_pressed_dt >= self.lever_press_interval: #if the time elapsed between lever presses is more than self.lever_press_interval, then administer a reward; note that this lever_press_interval is modifiable in session_info
                    print('reward_delivered')
                    self.pump.reward(self.reward_pump, self.reward_size)
                    self.lever_pressed_time = lever_pressed_time_temp #this is used for subsequent lever presses
                    self.total_reward += 1
        self.box.check_keybd()

    def enter_standby(self):
        logging.info(";" + str(time.time()) + ";[transition];enter_standby;" + str(self.error_repeat))
        self.update_plot_choice()
        self.trial_running = True #I UPDATED THIS TOO, SO THE RUN TASK LOGIC GETS RUN THROUGH
        print(str(time.time()) + ", Total reward up till current session: " + str(self.total_reward))
#         logging.info(";" + str(time.time()) + ";[trial];trial_" + str(self.trial_number) + ";" + str(self.error_repeat))

    def exit_standby(self):
        # self.error_repeat = False
        logging.info(";" + str(time.time()) + ";[transition];exit_standby;" + str(self.error_repeat))
        self.box.event_list.clear()
        pass

    def enter_reward_available(self):
        logging.info(";" + str(time.time()) + ";[transition];enter_reward_available;" + str(self.error_repeat))
        self.trial_running = True
        self.box.sound1.on() #ACTIVATE SOUND CUE#
        
    def exit_reward_available(self):
        logging.info(";" + str(time.time()) + ";[transition];exit_reward_available;" + str(self.error_repeat))
        self.pump.reward("vaccum", 0)
        self.box.sound1.off() #INACTIVATE SOUND CUE#

    def update_plot(self):
        fig, axes = plt.subplots(1, 1, )
        axes.plot([1, 2], [1, 2], color='green', label='test')
        self.box.check_plot(fig)

    def update_plot_error(self):
        error_event = self.error_list
        labels, counts = np.unique(error_event, return_counts=True)
        ticks = range(len(counts))
        fig, ax = plt.subplots(1, 1, )
        ax.bar(ticks, counts, align='center', tick_label=labels)
        # plt.xticks(ticks, labels)
        # plt.title(session_name)
        ax = plt.gca()
        ax.set_xticks(ticks, labels)
        ax.set_xticklabels(labels=labels, rotation=70)

        self.box.check_plot(fig)

    def update_plot_choice(self, save_fig=False):
        trajectory_active = self.left_poke_count_list
        time_active = self.timeline_left_poke
        trajectory_inactive = self.right_poke_count_list
        time_inactive = self.timeline_right_poke
        fig, ax = plt.subplots(1, 1, )
        print(type(fig))

        ax.plot(time_active, trajectory_active, color='b', marker="o", label='active_trajectory')
        ax.plot(time_inactive, trajectory_inactive, color='r', marker="o", label='inactive_trajectory')
        if save_fig:
            plt.savefig(self.session_info['basedir'] + "/" + self.session_info['basename'] + "/" +                         self.session_info['basename'] + "_lever_choice_plot" + '.png')
        self.box.check_plot(fig)

    def integrate_plot(self, save_fig=False):

        fig, ax = plt.subplots(2, 1)

        trajectory_left = self.active_press
        time_active_press = self.timeline_active_press
        trajectory_right = self.right_poke_count_list
        time_inactive_press = self.timeline_inactive_press
        print(type(fig))

        ax[0].plot(time_active_press, trajectory_left, color='b', marker="o", label='left_lick_trajectory')
        ax[0].plot(time_inactive_press, trajectory_right, color='r', marker="o", label='right_lick_trajectory')

        error_event = self.error_list
        labels, counts = np.unique(error_event, return_counts=True)
        ticks = range(len(counts))
        ax[1].bar(ticks, counts, align='center', tick_label=labels)
        # plt.xticks(ticks, labels)
        # plt.title(session_name)
        ax[1] = plt.gca()
        ax[1].set_xticks(ticks, labels)
        ax[1].set_xticklabels(labels=labels, rotation=70)

        if save_fig:
            plt.savefig(self.session_info['basedir'] + "/" + self.session_info['basename'] + "/" +                         self.session_info['basename'] + "_summery" + '.png')
        self.box.check_plot(fig)

    ########################################################################
    # methods to start and end the behavioral session
    ########################################################################

    def start_session(self):
        ic("TODO: start video")
        self.box.video_start()

    def end_session(self):
        ic("TODO: stop video")
        self.update_plot_choice(save_fig=True)
        self.box.video_stop()

