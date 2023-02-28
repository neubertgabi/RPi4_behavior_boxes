# put all of your mouse and session info in here

from datetime import datetime
import os
import pysistence, collections
import socket


# defining immutable mouse dict (once defined for a mouse, NEVER EDIT IT)
mouse_info = pysistence.make_dict({'mouse_name': 'DT000',
                 })

# Information for this session (the user should edit this each session)
session_info                              	= collections.OrderedDict()
session_info['mouse_info']					= mouse_info
session_info['mouse_name']                 	= mouse_info['mouse_name']
session_info['training_phase']             	= 1
session_info['basedir']					  	= '/home/pi/buffer'
session_info['external_storage']            = '/mnt/hd'
session_info['flipper_filename']            = '/home/pi/buffer/flipper_timestamp'
session_info['weight']                	    = 20.0
session_info['manual_date']					= '2022-06-27'
session_info['box_name']             		= socket.gethostname()

# session_info['config']						= 'freely_moving_v1'
session_info['config']						= 'head_fixed_go_nogo'
session_info['treadmill']                   = True

# universal parameters regardless of training phase
session_info['number_of_trials']            = 500  # total number of phase 2 trials
session_info['vacuum_length']               = 0.5  # in seconds
session_info['iti_length']                  = round((3 - session_info['vacuum_length']), 1)
session_info['reward_solenoid_duration'] = 0.020  # in seconds

# parameters for phase 0
session_info['number_of_phase0_trials']     = 500
session_info['RR_temp1_length']             = 10  # in seconds
session_info['RR_reward_collection_length'] = 2  # in seconds

# parameters for phase 1

# visual stimulus
session_info['gray_level']					= 40  # the pixel value from 0-255 for the screen between stimuli
session_info['vis_gratings_go']				= ['/home/pi/gratings/first_grating_go.dat']
session_info['vis_gratings_nogo']           = ['/home/pi/gratings/first_grating_nogo.dat']
session_info['vis_raws']					= []

