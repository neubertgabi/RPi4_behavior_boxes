# python3: headfixed_task.py
"""
author: tian qiu & Soyoun Kim
date: 2023-02-16
name: headfixed2FC_task.py
goal: model_free reinforcement learning behavioral training task structure
description:
    an updated test version of headfixed_task.py

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


class Headfixed2FCTask(object):
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
            State(name='standby',
                  on_enter=["enter_standby"],
                  on_exit=["exit_standby"]),
            Timeout(name="initiate",
                    on_enter=["enter_initiate"],
                    on_exit=["exit_initiate"],
                    timeout=self.session_info["initiation_timeout"],
                    on_timeout=["restart"]),
            Timeout(name='cue_state',
                    on_enter=["enter_cue_state"],
                    on_exit=["exit_cue_state"],
                    timeout=self.session_info["cue_timeout"],
                    on_timeout=["restart"]),
            Timeout(name='reward_available',
                    on_enter=["enter_reward_available"],
                    on_exit=["exit_reward_available"],
                    timeout=self.session_info["reward_timeout"],
                    on_timeout=["restart"])
        ]
        self.transitions = [
            ['start_trial', 'standby', 'initiate'],
            ['start_cue', 'initiate', 'cue_state'],
            ['evaluate_reward', 'cue_state', 'reward_available'],
            ['restart', ['initiate', 'cue_state', 'reward_available'], 'standby']
        ]

        self.machine = TimedStateMachine(
            model=self,
            states=self.states,
            transitions=self.transitions,
            initial='standby'
        )
        self.trial_running = False

        # trial statistics
        self.trial_number = 0
        self.error_count = 0
        self.error_list = []
        self.early_lick_error = False
        self.initiate_error = False
        self.cue_state_error = False
        self.wrong_choice_error = False
        self.multiple_choice_error = False
        self.error_repeat = False
        self.reward_time_start = None  # for reward_available state time keeping purpose
        self.reward_time = 10  # sec. could be incorporate into the session_info; available time for reward
        self.reward_times_up = False

        self.block_count = 0
        self.blocknumber = self.session_info["block_number"]
        self.current_card = None
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

        self.distance_initiation = self.session_info['treadmill_setup']['distance_initiation']
        self.distance_cue = self.session_info['treadmill_setup']['distance_cue']
        self.distance_buffer = None
        self.distance_diff = 0

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
        self.correct_trial_in_block = 0

    ########################################################################
    # functions called when state transitions occur
    ########################################################################
    def run(self):
        if self.box.event_list:
            self.event_name = self.box.event_list.popleft()
        else:
            self.event_name = ""
        # there can only be lick during the reward available state
        # if lick detected prior to reward available state
        # the trial will restart and transition to standby
        if self.event_name is "left_entry" or self.event_name == "right_entry":
            # print("EVENT NAME !!!!!! " + self.event_name)
            if self.state == "reward_available" or self.state == "standby" or self.state == "initiate":
                pass
            else:
                # print("beeeeeeep") # debug signal
                self.early_lick_error = True
                self.error_repeat = True
                self.restart()
        if self.state == "standby":
            pass
        elif self.state == "initiate":
            self.distance_diff = self.get_distance() - self.distance_buffer
            if self.distance_diff >= self.distance_initiation:
                self.initiate_error = False
                self.start_cue()
            else:
                self.initiate_error = True
        elif self.state == "cue_state":
            # if self.LED_blink:
            #     self.box.cueLED1.blink(0.2, 0.1)
            self.distance_diff = self.get_distance() - self.distance_buffer
            if self.distance_diff >= self.distance_cue:
                self.cue_state_error = False
                self.evaluate_reward()
            else:
                self.cue_state_error = True
        elif self.state == "reward_available":
            if not self.reward_times_up:
                if self.reward_time_start:
                    if time.time() >= self.reward_time_start + self.reward_time:
                        self.restart()
            # first detect the lick signal:
            cue_state = self.current_card[0]
            side_mice = None
            if self.event_name == "left_entry":
                side_mice = 'left'
                self.left_poke_count += 1
                self.left_poke_count_list.append(self.left_poke_count)
                self.timeline_left_poke.append(time.time())
            elif self.event_name == "right_entry":
                side_mice = 'right'
                self.right_poke_count += 1
                self.right_poke_count_list.append(self.right_poke_count)
                self.timeline_right_poke.append(time.time())
            if side_mice:
                self.side_mice_buffer = side_mice
                if cue_state == 'all':
                    side_choice = side_mice
                    if side_choice == 'left':
                        left_reward = self.session_info['reward_size'][self.current_card[2][0]]
                        reward_size = random.uniform(left_reward - self.session_info['reward_deviation'],
                                                     left_reward + self.session_info['reward_deviation'])
                        pump_num = self.current_card[3][0]
                    elif side_choice == 'right':
                        right_reward = self.session_info['reward_size'][self.current_card[2][1]]
                        reward_size = random.uniform(right_reward - self.session_info['reward_deviation'],
                                                     right_reward + self.session_info['reward_deviation'])
                        pump_num = self.current_card[3][1]
                else:
                    side_choice = self.current_card[1]
                    forced_reward = self.session_info['reward_size'][self.current_card[2]]
                    reward_size = random.uniform(forced_reward - self.session_info['reward_deviation'],
                                                 forced_reward + self.session_info['reward_deviation'])
                    pump_num = self.current_card[3]
                if side_mice == side_choice:  # if the animal chose correctly
                    print("Number of lick detected: " + str(self.lick_count))
                    if self.lick_count == 0:  # if this is the first lick
                        self.pump.reward(pump_num, reward_size)
                        self.total_reward += 1
                        self.correct_trial_in_block += 1
                        self.reward_time_start = time.time()
                        print("Reward time start" + str(self.reward_time_start))
                    self.lick_count += 1
                elif self.side_mice_buffer:
                    if self.lick_count == 0:
                        self.check_cue('sound2')
                        self.wrong_choice_error = True
                        self.restart()

        # look for keystrokes
        self.box.check_keybd()

    def enter_standby(self):
        logging.info(";" + str(time.time()) + ";[transition];enter_standby;" + str(self.error_repeat))
        self.update_plot_choice()
        # self.update_plot_error()
        self.trial_running = False
        # self.reward_error = False
        if self.early_lick_error:
            self.error_list.append("early_lick_error")
            self.early_lick_error = False
        self.lick_count = 0
        self.side_mice_buffer = None
        print(str(time.time()) + ", Total reward up till current session: " + str(self.total_reward))
        logging.info(";" + str(time.time()) + ";[trial];trial_" + str(self.trial_number) + ";" + str(self.error_repeat))

    def exit_standby(self):
        # self.error_repeat = False
        logging.info(";" + str(time.time()) + ";[transition];exit_standby;" + str(self.error_repeat))
        self.box.event_list.clear()
        pass

    def enter_initiate(self):
        # print("!!!!!!!!!!!event name is " + self.event_name) # for debugging purposes
        # check error_repeat
        logging.info(";" + str(time.time()) + ";[transition];enter_initiate;" + str(self.error_repeat))
        self.check_cue('sound1')
        self.trial_running = True
        # wait for treadmill signal and process the treadmill signal
        self.distance_buffer = self.get_distance()
        logging.info(
            ";" + str(time.time()) + ";[treadmill];" + str(self.distance_buffer) + ";" + str(self.error_repeat))

    def exit_initiate(self):
        # check the flag to see whether to shuffle or keep the original card
        logging.info(";" + str(time.time()) + ";[transition];exit_initiate;" + str(self.error_repeat))
        print("EVENT NAME: " + str(self.box.event_list))
        self.cue_off('sound1')
        if self.initiate_error:
            self.error_list.append('initiate_error')
            self.error_repeat = True
            logging.info(";" + str(time.time()) + ";[error];initiate_error;" + str(self.error_repeat))
            self.error_count += 1

    def enter_cue_state(self):
        logging.info(";" + str(time.time()) + ";[transition];enter_cue_state;" + str(self.error_repeat))
        # turn on the cue according to the current card
        self.check_cue(self.current_card[0])
        # wait for treadmill signal and process the treadmill signal
        self.distance_buffer = self.get_distance()
        logging.info(
            ";" + str(time.time()) + ";[treadmill];" + str(self.distance_buffer) + ";" + str(self.error_repeat))

    def exit_cue_state(self):
        logging.info(";" + str(time.time()) + ";[transition];exit_cue_state;" + str(self.error_repeat))
        self.cue_off(self.current_card[0])
        if self.cue_state_error:
            self.check_cue("sound2")
            self.error_list.append('cue_state_error')
            self.error_repeat = True
            logging.info(";" + str(time.time()) + ";[error];cue_state_error;" + str(self.error_repeat))
            self.error_count += 1
            self.cue_state_error = False

    def enter_reward_available(self):
        logging.info(";" + str(time.time()) + ";[transition];enter_reward_available;" + str(self.error_repeat))
        print(str(time.time()) + ", " + str(self.trial_number) + ", cue_state distance satisfied")
        self.cue_off(self.current_card[0])
        self.reward_times_up = False

    def exit_reward_available(self):
        logging.info(";" + str(time.time()) + ";[transition];exit_reward_available;" + str(self.error_repeat))
        self.reward_times_up = True
        self.pump.reward("vaccum", 0)
        if self.wrong_choice_error:
            logging.info(";" + str(time.time()) + ";[error];wrong_choice_error;" + str(self.error_repeat))
            self.error_repeat = True
            self.error_list.append('wrong_choice_error')
            self.wrong_choice_error = False
        elif self.lick_count == 0:
            logging.info(";" + str(time.time()) + ";[error];no_choice_error;" + str(self.error_repeat))
            self.error_repeat = True
            self.error_list.append('no_choice_error')
        else:
            logging.info(";" + str(time.time()) + ";[error];correct_trial;" + str(self.error_repeat))
            self.error_list.append('correct_trial')
        self.lick_count = 0
        self.reward_time_start = None

    def check_cue(self, cue):
        if cue == 'sound1':
            logging.info(";" + str(time.time()) + ";[cue];cue_sound1_on;" + str(self.error_repeat))
            self.box.sound1.on()
        if cue == 'sound2':
            logging.info(";" + str(time.time()) + ";[cue];cue_sound2_on;" + str(self.error_repeat))
            self.box.sound2.blink(1, 0.1, 1)
        elif cue == 'LED_L':
            self.box.cueLED1.on()
            logging.info(";" + str(time.time()) + ";[cue];cueLED_L_on;" + str(self.error_repeat))
        elif cue == 'LED_R':
            # self.LED_blink = True
            self.box.cueLED2.on()
            logging.info(";" + str(time.time()) + ";[cue];cueLED_R_on;" + str(self.error_repeat))
        elif cue == 'all':
            self.box.cueLED1.on()
            self.box.cueLED2.on()
            logging.info(";" + str(time.time()) + ";[cue];LED_L+R_on; " + str(self.error_repeat))

    def cue_off(self, cue):
        if cue == 'all':
            self.box.cueLED1.off()
            self.box.cueLED2.off()
        elif cue == 'sound1':
            self.box.sound1.off()
            logging.info(";" + str(time.time()) + ";[cue];cue_sound1_off;" + str(self.error_repeat))
        elif cue == 'sound2':
            self.box.sound2.off()
            logging.info(";" + str(time.time()) + ";[cue];cue_sound2_off;" + str(self.error_repeat))
        elif cue == 'LED_L':
            self.box.cueLED1.off()
            logging.info(";" + str(time.time()) + ";[cue];cueLED1_off;" + str(self.error_repeat))
        elif cue == 'LED_R':
            self.box.cueLED2.off()
            logging.info(";" + str(time.time()) + ";[cue];cueLED2_off;" + str(self.error_repeat))

    def get_distance(self):
        try:
            distance = self.treadmill.distance_cm
        except Exception as e:
            logging.info(";" + str(time.time()) + ";[system_error];" + str(e) + ";" + str(self.error_repeat))
            self.treadmill = self.box.treadmill
            distance = self.treadmill.distance_cm
        return distance

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
        ax = plt.gca()
        ax.set_xticks(ticks, labels)
        ax.set_xticklabels(labels=labels, rotation=70)

        self.box.check_plot(fig)

    def update_plot_choice(self, save_fig=False):
        trajectory_left = self.left_poke_count_list
        time_left = self.timeline_left_poke
        trajectory_right = self.right_poke_count_list
        time_right = self.timeline_right_poke
        fig, ax = plt.subplots(1, 1, )
        print(type(fig))

        ax.plot(time_left, trajectory_left, color='b', marker="o", label='left_lick_trajectory')
        ax.plot(time_right, trajectory_right, color='r', marker="o", label='right_lick_trajectory')
        if save_fig:
            plt.savefig(self.session_info['basedir'] + "/" + self.session_info['basename'] + "/" + \
                        self.session_info['basename'] + "_choice_plot" + '.png')
        self.box.check_plot(fig)

    def integrate_plot(self, save_fig=False):

        fig, ax = plt.subplots(2, 1)

        trajectory_left = self.left_poke_count_list
        time_left = self.timeline_left_poke
        trajectory_right = self.right_poke_count_list
        time_right = self.timeline_right_poke
        print(type(fig))

        ax[0].plot(time_left, trajectory_left, color='b', marker="o", label='left_lick_trajectory')
        ax[0].plot(time_right, trajectory_right, color='r', marker="o", label='right_lick_trajectory')

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
            plt.savefig(self.session_info['basedir'] + "/" + self.session_info['basename'] + "/" + \
                        self.session_info['basename'] + "_summery" + '.png')
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
