# Author: Pratik Singh
# Description: Model I

import os
import numpy
import json
import math
from nupic.engine import Network

import NetworkUtils

""" global data """
numRecords=0
_RECORD_SENSOR = "sensorRegion"
_L1_SPATIAL_POOLER = "l1SpatialPoolerRegion"
_L1_TEMPORAL_MEMORY = "l1TemporalMemoryRegion"
_L1_CLASSIFIER = "l1Classifier"

w, h = 7, 7
results = [[-1 for x in range(w)] for y in range(h)] 
l1ErrorSum = [-1 for x in range(h)]

def getOrCreateDataSource():
	fields=[]
	fields.append('cpu')
	names = []
	names.append('cpu')
	return NetworkUtils.getOrCreateDataSource(fields, names)
	
def BuildNetwork():	
	dataSource = getOrCreateDataSource()
	network = createOneLevelNetwork(dataSource)
	return dataSource, network
    
def runNetwork(network, dataSource, data, disableTraining, isTesting):
	
	#NetworkUtils.dataSource.data = data
	dataSource.setData(data)
	#dataSource.printData()
	if disableTraining == True:
		temporalMemoryRegion = network.regions[_L1_TEMPORAL_MEMORY]
		temporalMemoryRegion.setParameter("learningMode", False)
		l1Classifier = network.regions[_L1_CLASSIFIER]
		l1Classifier.setParameter('learningMode', False)
		
	return run(network, disableTraining, isTesting)
    
def createOneLevelNetwork(dataSource):
  
	network = Network()

	# Create and add a record sensor and a SP region
	sensor = NetworkUtils.createRecordSensor(network, name=_RECORD_SENSOR,
							  dataSource=dataSource)
	NetworkUtils.createSpatialPooler(network, name=_L1_SPATIAL_POOLER,
					  inputWidth=sensor.encoder.getWidth())

	# Link the SP region to the sensor input
	linkType = "UniformLink"
	linkParams = ""
	network.link(_RECORD_SENSOR, _L1_SPATIAL_POOLER, linkType, linkParams)

	# Create and add a TM region
	l1temporalMemory = NetworkUtils.createTemporalMemory(network, _L1_TEMPORAL_MEMORY)

	# Link SP region to TM region in the feedforward direction
	network.link(_L1_SPATIAL_POOLER, _L1_TEMPORAL_MEMORY, linkType, linkParams)

	# Add a classifier
	classifierParams = {  # Learning rate. Higher values make it adapt faster.
						'alpha': 0.005,

						# A comma separated list of the number of steps the
						# classifier predicts in the future. The classifier will
						# learn predictions of each order specified.
						'steps': '1,2,3,4,5,6,7',

						# The specific implementation of the classifier to use
						# See SDRClassifierFactory#create for options
						'implementation': 'py',

						# Diagnostic output verbosity control;
						# 0: silent; [1..6]: increasing levels of verbosity
						'verbosity': 0}

	l1Classifier = network.addRegion(_L1_CLASSIFIER, "py.SDRClassifierRegion",
								   json.dumps(classifierParams))
	l1Classifier.setParameter('inferenceMode', True)
	l1Classifier.setParameter('learningMode', True)
	network.link(_L1_TEMPORAL_MEMORY, _L1_CLASSIFIER, linkType, linkParams,
			   srcOutput="bottomUpOut", destInput="bottomUpIn")
	network.link(_RECORD_SENSOR, _L1_CLASSIFIER, linkType, linkParams,
			   srcOutput="categoryOut", destInput="categoryIn")
	network.link(_RECORD_SENSOR, _L1_CLASSIFIER, linkType, linkParams,
			   srcOutput="bucketIdxOut", destInput="bucketIdxIn")
	network.link(_RECORD_SENSOR, _L1_CLASSIFIER, linkType, linkParams,
			   srcOutput="actValueOut", destInput="actValueIn")

	steps = l1Classifier.getSelf().stepsList
	
	# initialize the results matrix, after the classifer has been defined
	w, h = len(steps), len(steps)+1
	global results
	results = [[-1 for x in range(w)] for y in range(h)] 
	global l1ErrorSum
	l1ErrorSum = [-1 for x in range(h-1)]
	
	print("Model Instantiated")
	
	return network

def run(network, disableTraining, isTesting):
	global numRecords
	global l1ErrorSum
	
	numRecords = numRecords + 1
	
	sensorRegion = network.regions[_RECORD_SENSOR]
	l1SpRegion = network.regions[_L1_SPATIAL_POOLER]
	l1TpRegion = network.regions[_L1_TEMPORAL_MEMORY]
	l1Classifier = network.regions[_L1_CLASSIFIER]
	
	if numRecords%NetworkUtils.saveFrequency == 0 and disableTraining == False:
		print("Saving the Model to file")
		NetworkUtils.SaveNetwork(network, "network1.nta")
	
	network.run(1)

	actual = float(sensorRegion.getOutputData("actValueOut")[0])
	l1Result, l1ResultConf = NetworkUtils.getPredictionResults(l1Classifier)
	steps = l1Classifier.getSelf().stepsList

	l1AnomalyScore = l1TpRegion.getOutputData("anomalyScore")[0]
	
	if disableTraining==False and isTesting == False: 
		print("record="+ str(numRecords))

	maxSteps = len(steps)
	for i in range(maxSteps):
		#shift the records
		if results[numRecords%(maxSteps)][i] != -1:
			l1ErrorSum[i] += math.fabs(results[numRecords%(maxSteps)][i] - actual)
		
		r = (steps[i]+numRecords)%(maxSteps)
		results[r][i] = l1Result[i]
	
	if disableTraining==False and isTesting == False:
		print("Actual Value: "+str(actual))
		print("Predicted: "+ str(results[numRecords%(maxSteps)]))
		print("Classifier Anomaly Score: "+ str(l1AnomalyScore))	
		print("Average Error: "+ str([x / numRecords for x in l1ErrorSum]))
		print("Current Predictions" + str(l1Result))
		
	predictions =results[numRecords%(maxSteps)]
	errorVal = str([x / numRecords for x in l1ErrorSum])
	
	return str(actual), predictions, errorVal, l1AnomalyScore

if __name__ == "__main__":
	dataSource, network = BuildNetwork()
	data = 54
	disableTraining = 0
	runNetwork(network, dataSource, data, disableTraining)
	print("done")
