import json
import glob
import os
import copy
from datetime import date
from datetime import timedelta

with open("templates/sim_template.json") as tplsimfile:
    tplsim = json.load(tplsimfile)

with open("templates/crop_template.json") as tplcrpfile:
    tplcrp = json.load(tplcrpfile)

sims_path = "sim_files/*.json"
#for sim_file in glob.glob(sims_path):    
#    with open(sim_file, "w") as f:
#        f.write(json.dumps(tplsim))
#print("sim files ready!")   

crops_path = "crop_files/*.json"
for crop_file in glob.glob(crops_path):  
    with open(crop_file, "r") as f:
        data = json.load(f)
        sowing_date = unicode(data["cropRotation"][0]["worksteps"][0]["date"])
        harvest_date = unicode(data["cropRotation"][0]["worksteps"][1]["date"])
        harv = harvest_date.split("-")
        new_harv_iso = (date(1999, int(harv[1]), int(harv[2])) + timedelta(5)).isoformat()[-5:]
        harvest_date = harvest_date[:5]+new_harv_iso
    with open(crop_file, "w") as f:
        tplcrp["cropRotation"][0]["worksteps"][0]["date"] = sowing_date
        tplcrp["cropRotation"][0]["worksteps"][1]["date"] = harvest_date
        f.write(json.dumps(tplcrp))
print("crop files ready!")
