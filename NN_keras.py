# from sklearn.mixture import GaussianMixture, BayesianGaussianMixture
import numpy as np
import pandas as pd
import conformer_utils as cu
import os
import time
import evaluation as eval

from keras import models
from keras import layers
from keras import optimizers
from keras import metrics
from keras import regularizers


def get_immediate_subdirectories(a_dir):
    return [name for name in os.listdir(a_dir)
            if os.path.isdir(os.path.join(a_dir, name))]


homeDir = "C:\\Users\\Etienne Bonanno\\Documents\\Conformers"

molfiles = [[homeDir + "\\" + x + "\\", x] for x in get_immediate_subdirectories(homeDir)]

def getKerasNNModel(descDim):
    INPUT_DIM = descDim

    model = models.Sequential()
    model.add(layers.Dense(100, activation='relu', input_dim=INPUT_DIM))
    model.add(layers.Dense(1, activation='linear', activity_regularizer=regularizers.l2(0.0001)))

    model.compile(optimizer='adam',
                  loss='mean_squared_error',
                  metrics=['accuracy'])

    return model


datasetPortion = [1, 0.8, 0.6, 0.5, 0.3, 0.1, 0.05, 10]

portionResults = []

for molNdx in range(0, len(molfiles)):
    molName = molfiles[molNdx][1]  # [molfiles[molNdx].rfind("/", 0, -1)+1:-1]
    for portion in datasetPortion:
        t0 = time.time()
        molNdx = 0
        descTypes = ["usr", "esh", "es5"]
        descType = descTypes[1]
        if portion <= 1:
            print("Loading " + str(portion * 100) + "% of " + molfiles[molNdx][1])
        else:
            print("Loading " + str(portion) + " actives from " + molfiles[molNdx][1])

        (test_ds, test_paths) = cu.loadDescriptors(molfiles[molNdx][0], portion * 0.2, dtype=descType,
                                                   active_decoy_ratio=-1, selection_policy="RANDOM",
                                                   return_type="SEPERATE")
        numcols = test_ds[0][0].shape[1] - 2

        folds = 2
        componentResults = []

        (n_fold_ds, n_fold_paths) = cu.loadDescriptors(molfiles[molNdx][0], portion * 0.8, dtype=descType,
                                                       active_decoy_ratio=-1,
                                                       selection_policy="RANDOM", return_type="SEPARATE",
                                                       exclusion_list=test_paths)

        (folds_list, excl_list) = cu.split(n_fold_ds, folds, policy="RANDOM")

        foldResults = []

        for fold in range(0, folds):

            val_ds = folds_list[fold]

            train_ds = None;

            for i in range(0, folds):
                if i != fold:
                    if train_ds is None:
                        train_ds = [r[0] for r in folds_list[i]]
                    else:
                        train_ds.append([r[0] for r in folds_list[i]])

            train_ds = cu.joinDataframes(train_ds)

            numcols = train_ds.shape[1] - 2

            ann = getKerasNNModel(numcols)
            ann.fit(train_ds.iloc[:, 0:numcols], ((train_ds["active"])).astype(int) * 100,
                    batch_size=500000,
                    epochs=1000)

            results = pd.DataFrame()

            results["score"] = [max(ann.predict(x[0].iloc[:, 0:numcols]).ravel()) for x in val_ds]
            results["truth"] = [x[2] for x in val_ds]
            auc = eval.plotSimROC(np.array(results["truth"]), np.array([results["score"]]), "", None)
            mean_ef = eval.getMeanEFs(np.array(results["truth"]), np.array([results["score"]]))
            foldResults.append((auc, mean_ef))

        print("X-Validation results: ")
        print(foldResults)

        if len(foldResults) > 0:
            mean_auc_sim = np.mean([x[0] for x in foldResults])
            std_auc_sim = np.std(np.mean([x[0] for x in foldResults]))
            mean_mean_ef_1pc = np.mean([x[1][0.01] for x in foldResults])
            std_mean_ef_1pc = np.std([x[1][0.01] for x in foldResults])
            mean_mean_ef_5pc = np.mean([x[1][0.05] for x in foldResults])
            std_mean_ef_5pc = np.std([x[1][0.05] for x in foldResults])

            print("mean AUC=" + str(mean_auc_sim) +
                  ", std=" + str(std_auc_sim) +
                  ", mean EF(1%)=" + str(mean_mean_ef_1pc) +
                  ", std=" + str(std_mean_ef_1pc) +
                  ", mean EF(5%)=" + str(mean_mean_ef_5pc) +
                  ", std=" + str(std_mean_ef_5pc))

            componentResults.append((molName, portion, auc, mean_ef))
        else:
            print("X-Validation returned no results. Skipping training...")
            componentResults.append((molName, portion, 0, 0))

        train_ds = cu.lumpRecords(n_fold_ds)
        ann = getKerasNNModel(numcols)
        ann.fit(train_ds.iloc[:, 0:numcols], ((train_ds["active"])).astype(int) * 100,
                batch_size=500000,
                epochs=1000)

        results = pd.DataFrame()

        results["score"] = [max(ann.predict(x[0].iloc[:, 0:numcols]).ravel()) for x in test_ds]
        # results["a_score"] = [G_a.score(x[0].iloc[:, 0:numcols]) for x in test_ds]
        results["truth"] = [x[2] for x in test_ds]  # np.array(test_ds)[:, 2]

        auc = eval.plotSimROC(results["truth"], [results["score"]], molName + "[ANN, " + str(portion * 100) + "%]",
                              molName + "_AMM_" + str(portion * 100) + ".pdf")
        mean_ef = eval.getMeanEFs(np.array(results["truth"]), np.array([results["score"]]))

        # print("Final results, num components = ", str(components)+": ")
        print("AUC(Sim)=" + str(auc))
        print("EF: ", mean_ef)

        portionResults.append((molName, portion, auc, mean_ef))
        t1 = time.time();
        print("Time taken = " + str(t1 - t0))

        print(componentResults)
        print(portionResults)

        # full_train_ds = test_ds
        # full_train_ds.extend(n_fold_ds)

        full_train_dss = [x[0] for x in test_ds]
        full_train_dss.append([x[0] for x in n_fold_ds])
        full_train_ds = cu.joinDataframes(full_train_dss)
        ann = getKerasNNModel(numcols)
        ann.fit(full_train_ds.iloc[:, 0:numcols], ((full_train_ds["active"])).astype(int) * 100, batch_size=200, epochs=1000)

        # serialize model to JSON
        model_json = ann.to_json()
        with open(molName + "_AMM.json", "w") as json_file:
            json_file.write(model_json)
        # serialize weights to HDF5
        ann.save_weights(molName + "_AMM.h5")
        print("Saved model for "+molName+" to disk")

