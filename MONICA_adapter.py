import json
import sys
sys.path.insert(0, "C:\\Users\\stella\\Documents\\GitHub\\monica\\project-files\\Win32\\Release")
sys.path.insert(0, "C:\\Users\\stella\\Documents\\GitHub\\monica\\src\\python")
import monica_io
import zmq
import csv
import os
from datetime import date
import collections


class monica_adapter(object):
    def __init__(self, exp_maps, obslist):

        #for multi-experiment: create a M-1 relationship between exp_IDs and param files
        self.IDs_paramspaths = {}
        for exp_map in exp_maps:
            self.IDs_paramspaths[exp_map["exp_ID"]] = {}
            self.IDs_paramspaths[exp_map["exp_ID"]]["species"] = exp_map["species_file"]
            self.IDs_paramspaths[exp_map["exp_ID"]]["cultivar"] = exp_map["cultivar_file"]

        #observations data structure for spotpy
        self.observations = []
        for obs in obslist:
            self.observations.append(obs["value"])

        self.species_params={} #map to store different species params sets avoiding repetition
        self.cultivar_params={} #map to store different cultivar params sets avoiding repetition

        #create envs
        self.envs = []
        for exp_map in exp_maps:
            with open(exp_map["sim_file"]) as simfile:
                sim = json.load(simfile)
                sim["crop.json"] = exp_map["crop_file"]
                sim["site.json"] = exp_map["site_file"]
                sim["climate.csv"] = exp_map["climate_file"]

            with open(exp_map["site_file"]) as sitefile:
                site = json.load(sitefile)
                site["SiteParameters"]["Latitude"] = exp_map["latitude"]

            with open(exp_map["crop_file"]) as cropfile:
                crop = json.load(cropfile)
                mycrop = crop["crops"].keys()[0]
                crop["crops"][mycrop]["cropParams"]["species"][1] = exp_map["species_file"]
                crop["crops"][mycrop]["cropParams"]["cultivar"][1] = exp_map["cultivar_file"]

            env = monica_io.create_env_json_from_json_config({
                "crop": crop,
                "site": site,
                "sim": sim
            })

            #add required outputs
            for record in obslist:
                if record["exp_ID"] == exp_map["exp_ID"]:
                    env["events"].append(unicode(record["date"]))
                    var = [unicode(record["variable"])]
                    env["events"].append(var)

            for ws in env["cropRotation"][0]["worksteps"]:
                if ws["type"] == "Seed":
                    self.species_params[exp_map["species_file"]] = ws["crop"]["cropParams"]["species"]
                    self.cultivar_params[exp_map["cultivar_file"]] = ws["crop"]["cropParams"]["cultivar"]
                    break

            monica_io.add_climate_data_to_env(env, sim)
            env["customId"] = exp_map["exp_ID"]
            self.envs.append(env)

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect("tcp://localhost:6666")

    def run(self, args):
        return self._run(*args)

    def _run(self, vector, user_params, calibrated_params):

        evallist = []
        out = {}

        #set params according to spotpy sampling. Update all the species/cultivar available
        for i in range(len(vector)):                        #loop on the vector
            par_name = user_params[i]["name"]
            for s in self.species_params:                   #loop on the species
                species = self.species_params[s]
                if par_name in species.keys():              #check for parameter existence in the dict
                    if user_params[i]["array"] == "FALSE":  #check the parameter is not part of an array   
                        species[par_name] = vector[i]
                    else:
                        arr_index = user_params[i]["array"]
                        species[par_name][int(arr_index)] = vector[i]
                else:
                    break                                   #break loop on species if the param is not there
            for cv in self.cultivar_params:                 #loop on the cultivars
                cultivar = self.cultivar_params[cv]
                if par_name in cultivar.keys():
                    if user_params[i]["array"] == "FALSE":
                        cultivar[par_name] = vector[i]
                    else:
                        arr_index = user_params[i]["array"]
                        if isinstance(cultivar[par_name][1], basestring):
                            #q&d way to understand if parameters' values are in a nested array (e.g., StageTemperatureSum)
                            #a better -and more generic- solution must be found!
                            cultivar[par_name][0][int(arr_index)] = vector[i]
                            #modify other TSUMS accordingly (specific for HS study)
                            if par_name == "StageTemperatureSum" and int(arr_index) == 2:
                                cultivar[par_name][0][0] = vector[i] * 0.389473684
                                cultivar[par_name][0][1] = vector[i] * 0.747368421
                            elif par_name == "StageTemperatureSum" and int(arr_index) == 3:
                                cultivar[par_name][0][4] = vector[i] * 2.333333333
                                cultivar[par_name][0][5] = vector[i] * 0.138888889
                                #assign values calibrated in the previous step (specific for HS study)
                                for cal_param in calibrated_params:
                                    if cal_param["name"] == "StageTemperatureSum" and cal_param["array"] == "2":
                                        cultivar[par_name][0][0] = cal_param["value"] * 0.389473684
                                        cultivar[par_name][0][1] = cal_param["value"] * 0.747368421
                                        cultivar[par_name][0][2] = cal_param["value"]
                                        break

                        else:
                            cultivar[par_name][int(arr_index)] = vector[i]
                else:
                    break

        for env in self.envs:
            species = self.species_params[self.IDs_paramspaths[env["customId"]]["species"]]
            cultivar = self.cultivar_params[self.IDs_paramspaths[env["customId"]]["cultivar"]]
            for ws in env["cropRotation"][0]["worksteps"]:
                if ws["type"] == "Seed":
                    ws["crop"]["cropParams"]["species"] = species
                    ws["crop"]["cropParams"]["cultivar"] = cultivar
                    break
            self.socket.send_json(env)
            rec_msg = self.socket.recv_json()

            results_rec = []
            for res in rec_msg["data"]:
                results_rec.append(res["results"][0][0])

            out[int(rec_msg["customId"])] = results_rec

        ordered_out = collections.OrderedDict(sorted(out.items()))
        for k, v in ordered_out.iteritems():
            for value in v:
                evallist.append(float(value))

        return evallist
