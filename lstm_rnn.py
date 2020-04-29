""" lstm_rnn.py
    -----------
    This script executes a long short term memory recurrent neural network to estimate the parameters of a parametric heavy tailed quantile
    function.

    Contact: nicolo.ceneda@student.unisg.ch
    Last update: 18 May 2020
"""


# -------------------------------------------------------------------------------
# 0. CODE SETUP
# -------------------------------------------------------------------------------


# Import the libraries

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import scipy.stats
import arch
import tensorflow as tf
import pyprind


# Set the seed

tf.random.set_seed(1)


# -------------------------------------------------------------------------------
# 1. PREPARE THE DATA
# -------------------------------------------------------------------------------


# Import the train, validation and test sets

symbol = 'AAPL'

X_train = pd.read_csv('datasets/mode sl/datasets std/' + symbol + '/X_train.csv')
X_valid = pd.read_csv('datasets/mode sl/datasets std/' + symbol + '/X_valid.csv')
X_test = pd.read_csv('datasets/mode sl/datasets std/' + symbol + '/X_test.csv')

Y_train = pd.read_csv('datasets/mode sl/datasets std/' + symbol + '/Y_train.csv')
Y_valid = pd.read_csv('datasets/mode sl/datasets std/' + symbol + '/Y_valid.csv')
Y_test = pd.read_csv('datasets/mode sl/datasets std/' + symbol + '/Y_test.csv')


# Reshape the train, validation and test subsets

elle = 200
n_features = 4

X_train = X_train.values.reshape(-1, elle, n_features)
X_valid = X_valid.values.reshape(-1, elle, n_features)
X_test = X_test.values.reshape(-1, elle, n_features)

Y_train = Y_train.values
Y_valid = Y_valid.values
Y_test = Y_test.values


# Create train, validation and test tensorflow datasets

batch_size = 100
""" PARAMS: 500, 1000 """

buffer_size = Y_train.shape[0]
""" PARAMS: 10000 """

ds_train = tf.data.Dataset.from_tensor_slices((X_train, Y_train))
ds_train = ds_train.shuffle(buffer_size).batch(batch_size, drop_remainder=True)
""" ALTERNATIVE: ds_train = ds_train.shuffle(10000).batch(batch_size).repeat() """

ds_valid = tf.data.Dataset.from_tensor_slices((X_valid, Y_valid))
ds_valid = ds_valid.batch(batch_size, drop_remainder=True)
""" ALTERNATIVE: ds_valid = ds_valid.batch(batch_size).repeat() """

ds_test = tf.data.Dataset.from_tensor_slices((X_test, Y_test))
ds_test = ds_test.batch(batch_size, drop_remainder=True)
""" ALTERNATIVE: ds_test = ds_test.batch(batch_size).repeat() """

for batch in ds_train.take(1):

    array_features = batch[0]
    array_targets = batch[1]

    print('The dataset is made up of several batches, each containing:'
          '\n- An array of time series of features: shape=', array_features.shape,
          '\n- An array of targets: shape=', array_targets.shape,
          '\n'
          '\nBatch 0'
          '\n-------',
          '\nTuple 0\n',
          array_features.numpy()[0], array_targets.numpy()[0],
          '\nTuple 999\n',
          array_features.numpy()[99], array_targets.numpy()[99])


# -------------------------------------------------------------------------------
# 2. DESIGN THE MODEL
# -------------------------------------------------------------------------------


# Create the model

A = 4
hidden_dim = 16
output_dim = 4

lstm_model = tf.keras.models.Sequential()
lstm_model.add(tf.keras.layers.LSTM(units=hidden_dim, return_sequences=False, input_shape=X_train.shape[-2:]))
lstm_model.add(tf.keras.layers.Dense(units=output_dim, activation='tanh'))
lstm_model.add(tf.keras.layers.Lambda(lambda x: x + np.array([0, 1, 1, 1])))


# Print the model summary

lstm_model.summary()

print('\nLSTM layer'
      '\n----------'
      '\nWeight kernel:            4(FE x HU)          = (FE x 4HU) =', lstm_model.weights[0].shape,
      '\nWeight recurrent kernel:  4(HU x HU)          = (HU x 4HU) =', lstm_model.weights[1].shape,
      '\nWeight bias:              4(BS x HU) = 4(HU,) = (4HU,)     =', lstm_model.weights[2].shape,
      '\n                                                             -------'
      '\nTotal                                                          1344')

print('\nDENSE layer'
      '\n-----------'
      '\nWeight kernel:                                              ', lstm_model.weights[3].shape,
      '\nWeight :                                                    ', lstm_model.weights[4].shape,
      '\n                                                             -------',
      '\nTotal                                                           68')


# Create additional variables

tau = tf.constant(np.concatenate(([0.01], np.divide(range(1, 20), 20), [0.99])).reshape(1, -1), dtype=tf.float32)
z_tau = tf.constant(scipy.stats.norm.ppf(tau, loc=0.0, scale=1.0), dtype=tf.float32)
tau_new = tf.constant(np.array([0.01, 0.05, 0.1]).reshape(1, -1), dtype=tf.float32)
z_tau_new = tf.constant(scipy.stats.norm.ppf(tau_new, loc=0.0, scale=1.0), dtype=tf.float32)


# Define the loss function that produces a scalar for each batch (Equation 60)

def q_calculator(Y_predicted):                                         # (BS x 4)

    mu = tf.reshape(Y_predicted[:, 0], [-1, 1])                        # (BS x 1)
    sig = tf.reshape(Y_predicted[:, 1], [-1, 1])                       # (BS x 1)
    u_coeff = tf.reshape(Y_predicted[:, 2], [-1, 1])                   # (BS x 1)
    d_coeff = tf.reshape(Y_predicted[:, 3], [-1, 1])                   # (BS x 1)
    u_factor = tf.exp(tf.matmul(u_coeff, z_tau)) / A + 1               # (BS x 1)(1 x n_z_tau) = (BS x n_z_tau)
    d_factor = tf.exp(-tf.matmul(d_coeff, z_tau)) / A + 1              # (BS x 1)(1 x n_z_tau) = (BS x n_z_tau)
    prod_factor = tf.multiply(u_factor, d_factor)                      # (BS x n_z_tau)*(BS x n_z_tau) = (BS x n_z_tau)
    q = tf.add(mu, tf.multiply(sig, tf.multiply(z_tau, prod_factor)))  # (BS x 1)+(BS x 1)*(1 x n_z_tau)*(BS x n_z_tau) = (BS x n_z_tau)

    return q


def pinball_loss_function(Y_actual, Y_predicted):

    q = q_calculator(Y_predicted)                                      # (BS x n_z_tau)
    error = tf.subtract(tf.cast(Y_actual, dtype=tf.float32), q)        # (BS x 1)-(BS x n_z_tau) = (BS x n_z_tau)
    error_1 = tf.multiply(tau, error)                                  # (1 x n_tau)*(BS x n_z_tau) = (BS x n_z_tau)
    error_2 = tf.multiply(tau - 1, error)                              # (1 x n_tau)*(BS x n_z_tau) = (BS x n_z_tau)
    loss = tf.reduce_mean(tf.maximum(error_1, error_2))                # (BS x n_z_tau) -> (1,)

    return loss


# Compile the model

lstm_model.compile(optimizer=tf.keras.optimizers.Adam(), loss=pinball_loss_function)


# -------------------------------------------------------------------------------
# 3. TRAIN THE MODEL
# -------------------------------------------------------------------------------


# Train the lstm recurrent neural network

n_epochs = 10
n_steps_per_epoch = 600
n_validation_steps = 100

history = lstm_model.fit(ds_train, epochs=n_epochs, validation_data=ds_valid)
""" ALTERNATIVE: 
   history = lstm_model.fit(ds_train, epochs=n_epochs, steps_per_epoch=n_steps_per_epoch,
                                          validation_data=ds_valid, validation_steps=n_validation_steps) 
"""


# Visualize the learning curve

hist = history.history

plt.figure()
plt.plot(hist['loss'], 'b')
plt.xlabel('Epoch')
plt.title('Training loss')
plt.tick_params(axis='both', which='major')
plt.tight_layout()
plt.savefig('images_lstm_rnn/train_loss.png')

plt.figure()
plt.plot(hist['val_loss'], 'r')
plt.xlabel('Epoch')
plt.title('Validation loss')
plt.tick_params(axis='both', which='major')
plt.tight_layout()
plt.savefig('images_lstm_rnn/valid_loss.png')


# -------------------------------------------------------------------------------
# 4. MAKE PREDICTIONS
# -------------------------------------------------------------------------------


# Predict the parameters and the quantiles

params_record_train = lstm_model.predict(X_train)
params_record_train = pd.DataFrame(params_record_train, columns=['mu', 'sigma', 'u_coeff', 'd_coeff'])  # (NB X 4) # TODO: BS vs number  of batches
q_record_train = q_calculator(params_record_train)
q_record_train = pd.DataFrame(q_record_train.numpy(), columns=tau.numpy().tolist()[0])                  # (NB x n_z_tau)

params_record_test = lstm_model.predict(X_test)                                                         # (BS X 4)
params_record_test = pd.DataFrame(params_record_test, columns=['mu', 'sigma', 'u_coeff', 'd_coeff'])
q_record_test = q_calculator(params_record_test)                                                        # (BS x n_z_tau)
q_record_test = pd.DataFrame(q_record_test.numpy(), columns=tau.numpy().tolist()[0])


# Save the predictions

results_folder = 'datasets/mode sl/results/' + symbol

if not os.path.isdir(results_folder):

    os.mkdir(results_folder)

params_record_train.to_csv(results_folder + '/params_record_train.csv', index=False)
q_record_train.to_csv(results_folder + '/q_record_train.csv', index=False)

params_record_test.to_csv(results_folder + '/params_record_test.csv', index=False)
q_record_test.to_csv(results_folder + '/q_record_test.csv', index=False)


# -------------------------------------------------------------------------------
# 5. BENCHMARK MODELS
# -------------------------------------------------------------------------------


garch_p = 3
garch_q = 3

model = arch.arch_model(Y, mean='Zero', vol='GARCH', dist='normal', p=3, q=3)
model_fit = model.fit()
yhat = model_fit.forecast(horizon=100)
plt.plot(yhat.variance.values[-1, :])

# -------------------------------------------------------------------------------
# 5. GENERAL
# -------------------------------------------------------------------------------


plt.show()


