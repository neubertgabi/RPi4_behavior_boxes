import rpg

# Define the "Go" stimulus
options_go = {"angle": 90, "spac_freq": 0.1, "temp_freq": 0.3, "duration": 3,  "contrast": 0, "percent_diameter": 50, "percent_center_left": 50, "percent_center_top": 50, "background": 0}
rpg.build_masked_grating("~/first_grating_go_round.dat", options_go)

# Define the "No-Go" stimulus - triangle


with rpg.Screen() as myscreen:
    grating_go = myscreen.load_grating("~/first_grating_go_round.dat")
    myscreen.display_grating(grating_go)
  
    grating_nogo = myscreen.load_grating("~/first_grating_nogo_triag.dat")
    myscreen.display_grating(grating_nogo)
