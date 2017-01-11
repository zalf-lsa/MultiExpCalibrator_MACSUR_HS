from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import spotpy
import spotpy_setup_MONICA
import os
import csv
from datetime import date
from datetime import timedelta
import numpy as np

basepath = os.path.dirname(os.path.abspath(__file__))

allparams = []
with open('calibratethese.csv') as paramscsv:
    reader = csv.reader(paramscsv)
    next(reader, None)  # skip the header
    for row in reader:
        p={}
        p["name"] = row[0]
        p["array"] = row[1]
        p["low"] = row[2]
        p["high"] = row[3]
        p["stepsize"] = row[4]
        p["optguess"] = row[5]
        p["minbound"] = row[6]
        p["maxbound"] = row[7]
        allparams.append(p)

#read phenology (specific for HS study calibration)
measured_pheno = {}
with open('WW_pheno_v3.csv') as phenofile:
    reader = csv.reader(phenofile)
    next(reader, None)  # skip the header
    for row in reader:
        location = row[3]
        measured_pheno[location] = {}
        measured_pheno[location]["flowering"] = int(row[7])
        measured_pheno[location]["harvest"] = int(row[8])

#read latitudes (specific for HS study calibration)
latitudes = {}
with open("JRC_soil_macsur_v3.csv") as latfile:
    reader = csv.reader(latfile)
    next(reader, None)  # skip the header
    for row in reader:
        location = row[3]
        latitudes[location] = float(row[5])

#assemble the problem (either single-experiment or multi-experiment)
sims_path = basepath + "\\sim_files"

filename = "optimized_params.csv" #file to store all the optimized params
with open(filename, 'wb') as opt_par_file:
    writer = csv.writer(opt_par_file)
    header = ["cell", "StageTemperatureSum_2", "StageTemperatureSum_3"]
    writer.writerow(header)

for root, dirs, filenames in os.walk(sims_path):
    for f in filenames:             #this way of defining the problem is specific for HS study, where each cell (e.g., sim file) is an independent experiment        
        calibrated_params = []      #this is to hold the value of calibrated params (!= from param file) for the following step in the loop
        
        cell = f[3:-5]
        splitcell = cell.split("_")
        if len(splitcell[1]) == 2:
            splitcell[1] = "0"+splitcell[1]
        climatefile = splitcell[0]+"_"+splitcell[1]+"_v1.csv"

        #define general settings
        exp_maps = []                                                   #list of maps needed in case of multi-experiment problems
        exp_map = {}
        exp_map["exp_ID"] = "0"                                         #in HS study there is only one "experiment" per cell
        exp_map["sim_file"] = basepath+"\\sim_files\\sim"+cell+".json"
        exp_map["crop_file"] = basepath+"\\crop_files\\crop"+cell+".json"
        exp_map["site_file"] = basepath+"\\site_files\\site.json"       #in HS study we use potential production for calibrating pheno --> no need to define specific soil(s)
        exp_map["latitude"] = latitudes[cell]                           #but latitude is important for photoperiod
        exp_map["climate_file"] = "Z:\\projects\\macsur-eu-heat-stress-assessment\\climate-data\\transformed\\0\\0_0\\"+climatefile
        exp_map["species_file"] = basepath+"\\param_files\\wheat.json"
        exp_map["cultivar_file"] = basepath+"\\param_files\\winter wheat.json"
        exp_maps.append(exp_map)

        filename = "opt_out/sim_vs_obs_"+cell+".csv"                    #file to store cell obs vs sims
        with open(filename, 'wb') as sim_obs_file:
            writer = csv.writer(sim_obs_file)
            header = ["date", "variable", "obs", "sim"]
            writer.writerow(header)        

        for phenopar in allparams:  #TSUM2 & TSUM3
            params = []
            params.append(phenopar) #calibration will be performed one parameter at a time

            #define observations
            obslist = []                        #this list will populate "events" region of the envs for retrieving outputs
            flowering_date = measured_pheno[cell]["flowering"]
            harvest_date = measured_pheno[cell]["harvest"]
            for i in range(1981, 2011):         #(specific for HS study) 
                dates = {}
                if phenopar["array"] == "2":    #pass flowering observations
                    dates[3] = (date(i, 1, 1) + timedelta(days=(flowering_date - 6))).isoformat()
                    dates[4] = (date(i, 1, 1) + timedelta(days=(flowering_date + 4))).isoformat()
                    x = 3
                    y = 5
                elif phenopar["array"] == "3":  #pass flowering observations
                    dates[5] = (date(i, 1, 1) + timedelta(days=(harvest_date - 6))).isoformat()
                    dates[6] = (date(i, 1, 1) + timedelta(days=(harvest_date + 4))).isoformat()
                    x = 5
                    y = 7
                for j in range(x, y):           #S3: preflowering, S4: postflowering, S5: grainfill, S6:senescence 
                    record = {}
                    record["exp_ID"] = "0"      #in HS study all the observations within a cell are related to a single experiment
                    record["date"] = dates[j]
                    record["variable"] = "Stage"
                    record["value"] = j
                    obslist.append(record)

            spot_setup = spotpy_setup_MONICA.spot_setup(params, exp_maps, obslist, calibrated_params)
            rep = 15
            results = []

            sampler = spotpy.algorithms.sceua(spot_setup, dbname='SCEUA', dbformat='ram')
            sampler.sample(rep, ngs=3, kstop=10)
            #sampler.sample(rep, ngs=3, kstop=50, pcento=0.01, peps=0.05)
            #sampler = spotpy.algorithms.lhs(spot_setup, dbname='LHS', dbformat='ram')
            #sampler.sample(rep)
            results.append(sampler.getdata())

            best = sampler.status.params

            this_param = {}
            this_param["name"] = phenopar["name"]
            this_param["array"] = phenopar["array"]
            this_param["value"] = best[0]
            calibrated_params.append(this_param) #save param for next step
            #print(f, best)

            for result in results[0]:
                if result[1] == best[0]:
                    estimated = []
                    for i in range(len(params)+1, len(result)-1):
                        estimated.append(result[i])
                    break

            filename = "opt_out/sim_vs_obs_"+cell+".csv"
            with open(filename, 'ab') as sim_obs_file:
                writer = csv.writer(sim_obs_file)
                for i in range(len(obslist)):
                    outrow = []
                    outrow.append(str(obslist[i]["date"]))
                    outrow.append(str(obslist[i]["variable"]))
                    outrow.append(str(obslist[i]["value"]))
                    outrow.append(str(estimated[i]))
                    writer.writerow(outrow)
            
            if(phenopar["array"] == "3"):       #second optimization, save optimized params
                filename = "optimized_params.csv"
                with open(filename, 'ab') as opt_par_file:
                    writer = csv.writer(opt_par_file)                    
                    outrow = []
                    outrow.append(str(cell))
                    outrow.append(str(calibrated_params[0]["value"]))
                    outrow.append(str(calibrated_params[1]["value"]))
                    print(cell + " optimized params " + str(calibrated_params[0]["value"]) + ", "+ str(calibrated_params[1]["value"]))
                    writer.writerow(outrow)
