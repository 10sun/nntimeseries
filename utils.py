# -*- coding: utf-8 -*-
"""
Created on Thu Dec 15 13:57:01 2016

@author: mbinkowski

The utilities file.

The file contains i.a. the ModelRunner and Generator classes.
"""
from __init__ import *

def list_of_param_dicts(param_dict):
    """
    Function to convert dictionary of lists to list of dictionaries of
    all combinations of listed variables. Example
    list_of_param_dicts({'a': [1, 2], 'b': [3, 4]})
        [{'a': 1, 'b': 3}, {'a': 1, 'b': 4}, {'a': 2, 'b': 3}, {'a': 2, 'b': 4}]
    """
    vals = list(prod(*[v for k, v in param_dict.items()]))
    keys = list(prod(*[[k]*len(v) for k, v in param_dict.items()]))
    return [dict([(k, v) for k, v in zip(key, val)]) for key, val in zip(keys, vals)]

        
def get_param_no(nn):
    return int(np.sum([np.sum([np.prod(K.eval(w).shape) for w in l.trainable_weights]) for l in nn.layers]))
    
    
class ModelRunner(object):
    """
    Class that defines a grid-search task with specified hyperparameters and 
    datasets.
    Initialization arguments:
        param_dict  - dictionary of the form {param_name: param_list, ...}
                      where 'param_list' is a list of values for parameter 
                      'param_name' to search over
        data_list   - list of datasets to test. Each dataset should have a form
                      of valid input to the model input function                    
        model       - function defining model to evaluate; should take 2 
                      arguments, first of which has to be a dictionary of the 
                      form {param_name, param_value} and second of arbitrary form
        save_file   - path to the file to save_results in 
        hdf5_dir    - directory to save trained models using keras Model.save()
                      method
    """    
    def __init__(self, param_dict, data_list, model, save_file, 
                 hdf5_dir='hdf5_keras_model_files'):
        self.param_list = list_of_param_dicts(param_dict)
        self.data_list = data_list
        self.model = model
        self.save_file = WDIR + '/' + save_file
        self.cdata = None
        self.cp = None
        self.cresults = None
        self.time0 = time.time()
        self.hdf5_dir = WDIR + '/' + hdf5_dir
        if hdf5_dir not in os.listdir(WDIR):
            os.mkdir(self.hdf5_dir)
        
    def _read_results(self):
        if self.save_file.split('/')[-1] in os.listdir('/'.join(self.save_file.split('/')[:-1])):
        #    results = []
            results = [v for k, v in pd.read_pickle(self.save_file).T.to_dict().items()]
        else:
            results = []
        return results
    
    def _get_hdf5_name(self):
        n = 0
        files = os.listdir(self.hdf5_dir)
        if len(files) > 0:
            n = int(np.max([int(f.split('_')[0]) for f in files])) + 1
        t = datetime.datetime.now().isoformat().replace(':', '.')
        code = ''.join(np.random.choice([l for l in string.ascii_uppercase], 5))
        return '%s/%06d_%s_%s_RunMod.h5' % (self.hdf5_dir, n, t, code)
    
    def run(self, trials=3, log=False, read_file=None, limit=1, irrelevant=[]):
        """
        Function that launches grid search, saves and returns results.
        Arguments:
            trials      - (int) number of trials to succesfully run single 
                          model setting; when number of errors exceeds 'trials'
                          grid serach goes to the next hyperparameter setting
            log         - if True, stdout is passed to the log file saved in
                          logs directory
            read_file   - file to read the previously computed results from.
                          If a setting has already been tested enough many 
                          times, grid serach passes to the next setting
            limit       - required number of successful runs for each single
                          parameter setting
            irrelevant  - list of paramters irrelevant while comparing a 
                          setting with the previously computed results. This
                          parameter has no impact if read)file is not specified
        Returns
            list of dictionaries; each dictionary contains data from keras 
            History.history dicttionary, parameter dictionary and other data
        """
        if log:
            old_stdout = sys.stdout
            log_name = self.save_file.replace('results', 'logs')[:-4]   
            log_file = open(log_name + time.strftime("%x").replace('/', '.') + '.txt', 'w', buffering=1)
            sys.stdout = log_file
        self.cresults = self._read_results()
        unsuccessful_settings = []
        for params in self.param_list:
            for data in self.data_list:
                if limit < np.inf:
                    already_computed = self.lookup_setting(read_file=read_file,
                                                           params=params, data=data,
                                                           irrelevant=irrelevant)
                    if already_computed >= limit:
                        print('Found %d (>= limit = %d) computed results for the setting:' % (already_computed, limit))
                        print([data, params])
                        continue
                    else:
                        required_success = limit - already_computed
                        print('Found %d (< limit = %d) computed results for the setting.' % (already_computed, limit))
                else:
                    required_success = 1
                success, errors = 0, 0
                setting_time = time.time()
                while (errors < trials) and (success < required_success):
#                    try:
                    print(data + ' success: %d, errors: %d' % (success, errors))
                    print(params)
                    self.cdata = data
                    self.cp = params
                    history, nn, reducer = self.model(data, params)
                    self.nn = nn
                    self.reducer = reducer
                    self.history = history
                    model_results = history.history
                    model_results.update(params)
                    hdf5_name = self._get_hdf5_name()
                    print('setting time %.2f' % (time.time() - setting_time))
                    nn.save(hdf5_name)
                    model_results.update(
                        {'training_time': time.time() - setting_time,
                         'datetime': datetime.datetime.now().isoformat(),
                         'dt': datetime.datetime.now(),
                         'date': datetime.date.today().isoformat(),
                         'data': data,
                         'hdf5': hdf5_name,
                         'total_params': np.sum([np.sum([np.prod(K.eval(w).shape) for w in l.trainable_weights]) for l in nn.layers])
#                             'json': nn.to_json(),
#                             'model_params': reducer.saved_layers
                         }
                    )
                    self.cresults.append(model_results)
                    pd.DataFrame(self.cresults).to_pickle(self.save_file)
                    success += 1
#                    except Exception as e:
#                        errors += 1
#                        print(e)
                if success < required_success:
                    unsuccessful_settings.append([data, params])
        #    with open(save_file, 'wb') as f:
        #        pickle.dump(results, f)
        with open(self.save_file[:-4] + 'failed.pikle', 'wb') as f:
            pickle.dump(unsuccessful_settings, f)
        if log:
            sys.stdout = old_stdout
            log_file.close()
        return self.cresults
        
    def lookup_setting(self, read_file, params, data, irrelevant):
        """
        Function that counts already computed results .
        Arguments:
            read_file   - file to read the previously computed results from
            params      - a dictionary of parameters to look for
            data        - dataset for which to look for
            irrelevant  - list of paramters irrelevant while comparing  
                          'params' with the previously computed results
        Returns
            number of times the given (parameter, data) setting occurs in
            training data saved in read_file
        """
        if read_file is None:
            already_computed = self.cresults
        else:
            already_computed = [v for k, v in pd.read_pickle(WDIR + '/' + read_file).T.to_dict().items()]
        count = 0
        for res in already_computed:
            if res['data'] != data:
                continue
            par_ok = 1
            for k, v in params.items():
                if k in irrelevant:
                    continue
                if k not in res:
                    par_ok = 0
                    break
                if res[k] != v:
                    par_ok = 0
                    break
            count += par_ok
        return count

class Generator(object):
    """
    Class that defines a generator that produces samples for fit_generator
    method of the keras Model class.
    Initialization arguments:
        X               - (pandas.DataFrame) data table
        train_share     - tuple of two numbers in range (0, 1) that provide % limits 
                      for training and validation samples
        input_length    - no. of timesteps in the input
        output_length   - no. of timesteps in the output
        verbose         - level of verbosity (corresponds to keras use of 
                          verbose argument)
        limit           - maximum number of timesteps-rows in the 'X' DataFrame
        batch_size      - batch size
        excluded        - columns from X to exclude
        diffs           - if True, X is replaced with table of 1st differences
                          of the input series
    """
    def __init__(self, X, train_share=(.8, 1), input_length=1, output_length=1, 
                 verbose=1, limit=np.inf, batch_size=16, excluded=[], 
                 diffs=False):
        self.X = X
        self.diffs = diffs
        if limit < np.inf:
            self.X = self.X.loc[:limit]
        self.train_share = train_share
        self.input_length = input_length
        self.output_length = output_length
        self.l = input_length + output_length
        self.verbose = verbose
        self.batch_size = batch_size
        self.n_train = int(((self.X.shape[0] - diffs) * train_share[0] - self.l)/batch_size) * batch_size + self.l
        self.n_all = self.n_train + int(((self.X.shape[0] - diffs) * train_share[1] - self.n_train - self.l)/batch_size) * batch_size + self.l
        self.excluded = excluded
        self.cols = [c for c in self.X.columns if c not in self.excluded]
        self._scale()
    
    def asarray(self, cols=None):
        if cols is None:
            cols = self.cols
        return np.asarray(self.X[cols], dtype=np.float32)

    def get_target_col_ids(self, ids=True, cols='default'):
        if cols in ['default', 'all']:
            if ids:
                return np.arange(len(self.cols))
            else:
                return self.cols
        elif hasattr(cols, '__iter__'):
            if type(cols[0]) == str:
                return [(i if ids else c) for i, c in enumerate(self.cols) if c in cols]
            elif type(cols[0]) in [int, float]:
                return [(int(i) if ids else self.cols[int(i)]) for i in cols]
            else:
                raise Exception('cols = ' + repr(cols) + ' not supported')
        else:
            raise Exception('cols = ' + repr(cols) + ' not supported')

    def get_dim(self):
        return self.asarray().shape[1]

    def get_dims(self, cols='default'):
        return self.get_dim(), len(self.get_target_col_ids(cols=cols))
        
    def exclude_columns(self, cols):
        self.excluded += cols
        
    def _scale(self, exclude=None, exclude_diff=None):
        if exclude is None:
            exclude = self.excluded
        cols = [c for c in self.X.columns if c not in exclude]
        if self.diffs:
            diff_cols = [c for c in self.X.columns if c not in exclude_diff]
            self.X.loc[:, diff_cols] = self.X.loc[:, diff_cols].diff()
            self.X = self.X.loc[self.X.index[1:]]
        self.means = self.X.loc[:self.n_train, cols].mean(axis=0)
        self.stds = self.X.loc[:self.n_train, cols].std(axis=0)
        self.X.loc[:, cols] = (self.X[cols] - self.means)/(self.stds + (self.stds == 0)*.001)
        
    def gen(self, mode='train', batch_size=None, func=None, shuffle=True, 
            n_start=0, n_end=np.inf):
        """
        Function that yields possibly infinitely many training/validation 
        samples.
        Arguments:
            mode        - if 'train' or 'valid', the first and last indices of 
                          returned timesteps are within boundaries defined by 
                          train_share at initilization; if 'manual' n_start and
                          n_end have to be provided
           batch_size   - if None, self.batch_size is used
           func         - function that is applied to each output sample;
                           can provide formatting or discarding certain dimentions
                          default: 
                              lambda x: (x[:, :self.input_length, :], 
                                         x[:, self.input_length:, :])
            shuffle     - wheather or not to shuffle samples every training epoch
            n_start, n_end - lower and upper limits of timesteps to appear in 
                             the generated samples. Irrelevant if mode != 'manual
        Yields
            sequence of samples func(x) where x is a numpy.array of consecutive 
            rows of X
                          
        """
        if batch_size is None:
            batch_size = self.batch_size
        if func is None:
            func = lambda x: (x[:, :self.input_length, :], x[:, self.input_length:, :])
        if mode=='train':
            n_end = self.n_train
        elif mode == 'valid':
            n_start = self.n_train
            n_end = self.n_all
        elif mode == 'manual':
            assert n_end < self.n_all
            assert n_start >= 0
            assert n_end > n_start
        else:
            raise Exception('invalid mode')
        if not shuffle:
            if (n_end - n_start - self.l) % batch_size != 0:
                raise Exception('For non-shuffled input (for RNN) batch_size must divide n_end - n_start - self.l')
            if mode == 'valid':
                n_start -= self.l - 1
                n_end -= self.l - 1
        XX = self.asarray()
        x = []
        while True:
            order = np.arange(n_start + self.input_length, n_end - self.output_length)
            if shuffle:
                order = np.random.permutation(order)
            else:
                order = order.reshape(batch_size, len(order)//batch_size).transpose().ravel()
            for i in order:
                if len(x) == batch_size:
                    yield func(np.array(x))
                    x = []
                x.append(XX[i - self.input_length: i + self.output_length, :])
    
    def make_io_func(self, io_form, cols='default', input_cols=None):
        """
        Function that defines input/output format function to be passed to 
        self.gen.
        Arguments:
            io_form     - string indicating input/output format
                'flat_regression': returns pair of 2d np.arrays (no time 
                                   dimension, only batch x sample_size)
                                   appropriate for Linear Regression
                'regression':      returns tuple (3d np.array, 2d np.array)
                                   first array formatted for LSTM and CNN nets
                'vi_regression':   format for SOCNN network wihtout auxiliary
                                   output
                'cvi_regression':  format for SOCNN network with auxiliary
                                   output   
            cols        - list of output column names (as of self.X DataFrame)
                          if 'default' all columns are passed
            input_cols  - list of input columns indices (as of self.X DataFrame)
                          if None all columns are passed
        Returns
            function that takes a numpy array as an input and returns 
            appropriately formatted input (usually as required by the keras 
            model)
                          
        """
        cols = self.get_target_col_ids(cols)
        il = self.input_length
        if io_form == 'regression':
            def regr(x):
                osh = (x.shape[0], (x.shape[1] - il) * len(cols))
                return (x[:, :il, :] if (input_cols is None) else x[:, :il, input_cols], 
                        x[:, il:, cols].reshape(osh))
            return regr
        
        elif io_form == 'flat_regression':
            def regr(x):
                if input_cols is None:
                    ish = (x.shape[0], il * x.shape[2])
                    inp =  x[:, :il, :]
                else:
                    ish = (x.shape[0], il * len(input_cols))
                    inp = x[:, :il, input_cols]
                osh = (x.shape[0], (x.shape[1] - il) * len(cols))              
                return (inp.reshape(ish), 
                        x[:, il:, cols].reshape(osh))
            return regr
    
        elif io_form == 'vi_regression':
            def regr(x):
        #        osh = (x.shape[0], (x.shape[1] - il) * len(cols))
                return ({'inp': x[:, :il, :] if (input_cols is None) else x[:, :il, input_cols], 
                         'value_input': x[:, :il, cols]},
                        x[:, il:, cols])
            return regr
        
        elif io_form == 'cvi_regression':
            def regr(x):
        #        osh = (x.shape[0], (x.shape[1] - il) * len(cols))
                return (
                    {'inp': x[:, :il, :] if (input_cols is None) else x[:, :il, input_cols], 
                     'value_input': x[:, :il, cols]},
                    {'main_output': x[:, il:, cols],
                     'value_output': np.concatenate(il*[x[:, il: il+1, cols]], axis=1)}
                )           
            return regr
        else:
            raise Exception('io_form' + repr(io_form) + 'not implemented')
        