import numpy as np
import json
import scipy as sp
from sklearn import linear_model
from pymongo import MongoClient
import sys
import cherrypy
from cherrypy import tools

# DB stuff
client = MongoClient()
db = client.lmi
coll = db.skills

# Store numpy arrays for all skills data in memory
skills = list(coll.find())
for i in range(len(skills)):
    skills[i]["data"] = np.array(skills[i]["data"])

# Predict new careers (onet codes) based on a set of skills data
def predict(data, epsilon=0.01, limit=5):
    # Split passed data into x/y
    num_params = np.shape(data)[1] - 1
    X = data[:,:num_params]
    y = data[:,num_params]
    orig_y = y.copy()

    # Inverse logistic on Y
    # Cap with epsilon
    for i in range(len(y)):
        if y[i] == 0: y[i] = epsilon
        elif y[i] == 1: y[i] = 1 - epsilon
    y = -np.log(1/y-1)

    # Linear regression on (X, in_lo Y)
    # clf = linear_model.Ridge(alpha=.5)
    clf = linear_model.RidgeCV(alphas=[0.1,0.5,1.0,10.0])
    clf.fit(X, y)
    print "Alpha: %.2f" % clf.alpha_
    print "Model: " + str(clf.coef_)

    # Accuracy
    correct = 0
    incorrect = 0
    for i in range(len(X)):
        # Predicted continuous value
        val = clf.predict(X[i])
        # 'Logisticise'
        rating = 1 if (1/(1+np.exp(-val)) > 0.5) else 0
        if rating == orig_y[i]: correct += 1
        else: incorrect += 1
    accuracy = (correct*1.0/(correct+incorrect))
    print "Accuracy: %.2f%%" % (accuracy*100)

    # Maximise by brute-forcing over existing data
    min_error = float("inf")
    best_skills = sorted(skills, key = lambda s: clf.predict(s['data']), reverse=True)[:limit]
    best_skills_data = []
    for s in best_skills:
        best_skills_data += [{'onet': s['onet'], 'soc': s['soc'], 'prediction': '%.2f%%' % (clf.predict(s['data'])*100)}]

    # Maximise model output (within bounds of ...)
    # Can only minimise so flip signs
    # def predict(x):
        # return -clf.predict(x)

    # bounds = [(0,7)]*num_params
    # initial_guess = [3.5] * num_params
    # result = sp.optimize.minimize(predict, initial_guess, bounds=bounds)
    # print "Optimum values: " + str(result.x)
    # print "Prediction: %.2f%%" % (-100.0*result.fun)

    return {'skills': best_skills_data, 'accuracy': accuracy, 'optimum': list(best_skills[0]['data'])}

    # return result.x


class API(object):
    @tools.json_out()
    def index(self, data=[], limit=5, epsilon=0.01):
        # input_data = np.loadtxt("data.txt")
        input_data = []
        for (onet_code, chosen) in json.loads(data):
            record = coll.find({'onet': onet_code})[0]
            datum = record['data'] + [float(chosen)]
            input_data += [datum]
        input_data = np.array(input_data)
        # input_data = np.array(json.loads(data))
        return predict(input_data, limit=int(limit), epsilon=float(epsilon))
    index.exposed = True

cherrypy.server.socket_host = '0.0.0.0'
cherrypy.quickstart(API())
