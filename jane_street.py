# -*- coding: utf-8 -*-
"""Jane_Street.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1x2UKiCkS8BmaLlxfIjFPywVbCO8EH4xx
"""

!pip install dask dask_ml xgboost

import os

kaggle_dir = '/root/.kaggle'
os.makedirs(kaggle_dir, exist_ok=True)

!cp kaggle.json {kaggle_dir}/

!kaggle competitions download -c jane-street-real-time-market-data-forecasting

!unzip jane-street-real-time-market-data-forecasting.zip

!rm jane-street-real-time-market-data-forecasting.zip

import dask.dataframe as dd
from xgboost.dask import DaskXGBRegressor
from dask_ml.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from dask_ml.model_selection import train_test_split
import pandas as pd
import numpy as np

# Define features and target
target = 'responder_6'
features = [f"feature_{i:02d}" for i in range(79)] + ["date_id", "time_id", "symbol_id"]

# Define the imputer
imputer = SimpleImputer(strategy='constant', fill_value=0)

# Read the data
data_dir = '/content/train.parquet'
data = dd.read_parquet(f"{data_dir}/*/*", columns=features + [target] + ['weight'])
# Impute missing values
def impute_partition(df):
    # Convert the numpy array back to a DataFrame with the original columns
    imputed_array = imputer.fit_transform(df)
    return pd.DataFrame(imputed_array, columns=df.columns)

data = data.map_partitions(impute_partition)

# Save the imputed dataset
data.to_parquet("imputed_dataset")

from dask.distributed import Client, LocalCluster

# Create a local cluster
cluster = LocalCluster()
client = Client(cluster)

print(client)

data_dir = '/content/imputed_dataset'
data = dd.read_parquet(f"{data_dir}/*")
data = data.sort_values(by=["date_id", "time_id"]).reset_index(drop=True)


X = data[features]
Y = data[target]
weights = data['weight']


num_valid_dates = 100
dates = data['date_id'].unique().compute()
valid_dates = dates[-num_valid_dates:]
train_dates = dates[:-num_valid_dates]

train_mask = data['date_id'].isin(train_dates)
valid_mask = data['date_id'].isin(valid_dates)

X_Train = X[train_mask]
Y_Train = Y[train_mask]
X_Valid = X[valid_mask]
Y_Valid = Y[valid_mask]

dask_model = DaskXGBRegressor(
    objective="reg:squarederror",
    n_estimators=1000,
    max_depth=6,
    learning_rate=0.1,
    tree_method="hist"
)

dask_model.fit(X_Train, Y_Train)

def compute_weighted_r2(y_true, y_pred, weights):
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    weights = np.array(weights)

    # Zero-mean adjustment for y_true
    y_true_zero_mean = y_true - np.average(y_true, weights=weights)

    # Calculate numerator and denominator
    numerator = np.sum(weights * (y_true - y_pred) ** 2)
    denominator = np.sum(weights * (y_true_zero_mean) ** 2)

    # Compute R^2 score
    r2_score = 1 - numerator / denominator
    return r2_score



print(Y_Valid, dask_model.predict(X_Valid), weights)


test_data_dir = '/content/test.parquet/date_id=0/part-0.parquet'
test_data = dd.read_parquet(f"{data_dir}", columns=features + [target])



prediction = dask_model.predict(test_data)

prediction.to_csv("predictions.csv", index=True, header=True)