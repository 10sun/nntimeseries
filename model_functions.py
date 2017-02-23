# -*- coding: utf-8 -*-
"""
Created on Thu Feb 23 20:38:16 2017

@author: mbinkowski
"""

from __init__ import *
from artificial_data_utils import ArtificialGenerator as generator

def CVI2model(datasource, params):
    globals().update(params)
    G = generator(filename=datasource, train_share=train_share, 
            input_length=input_length, 
            output_length=output_length, verbose=verbose,
            batch_size=batch_size, diffs=diffs)
    
    dim = G.get_dim()
    cols = G.get_target_cols()
    regr_func = G.make_io_func(io_form='cvi_regression', cols=target_cols)

    inp = Input(shape=(input_length, dim), dtype='float32', name='inp')
    value_input = Input(shape=(input_length, len(cols)), dtype='float32', name='value_input')
    
    offsets = [inp]
    sigs = [inp]
    loop_layers = {}
    
    for j in range(layers_no['sigs']):
        # significance
        name = 'significance' + str(j+1)
        ks = kernelsize[j % len(kernelsize)] if (type(kernelsize) == list) else kernelsize
        loop_layers[name] = Convolution1D(filters if (j < layers_no['sigs'] - 1) else len(cols), 
                                          filter_length=ks, border_mode='same', 
                                          activation='linear', name=name,
                                          W_constraint=maxnorm(norm))
        sigs.append(loop_layers[name](sigs[-1]))
        
        loop_layers[name + 'BN'] = BatchNormalization(name=name + 'BN')
        sigs.append(loop_layers[name + 'BN'](sigs[-1]))
        
        # residual connections
        if resnet and (connection_freq > 0) and (j > 0) and ((j+1) % connection_freq == 0):
            sigs.append(merge([sigs[-1], sigs[-3 * connection_freq + (j==1)]], mode='sum', 
                               concat_axis=-1, name='significance_residual' + str(j+1)))
                       
        loop_layers[name + 'act'] = LeakyReLU(alpha=.1, name=name + 'act') if (act == 'leakyrelu') else Activation(act, name=name + 'act')
        sigs.append(loop_layers[name + 'act'](sigs[-1]))
    
    for j in range(layers_no['offs']):
        # offset
        name = 'offset' + str(j+1)
        loop_layers[name] = Convolution1D(filters if (j < layers_no['offs'] - 1) else len(cols),
                                          filter_length=1, border_mode='same', 
                                          activation='linear', name=name,
                                          W_constraint=maxnorm(norm))
        offsets.append(loop_layers[name](offsets[-1]))
        
        loop_layers[name + 'BN'] = BatchNormalization(name=name + 'BN')
        offsets.append(loop_layers[name + 'BN'](offsets[-1]))
        
        # residual connections
        if resnet and (connection_freq > 0) and (j > 0) and ((j+1) % connection_freq == 0):
            offsets.append(merge([offsets[-1], offsets[-3 * connection_freq + (j==1)]], mode='sum', 
                                  concat_axis=-1, name='offset_residual' + str(j+1)))
                        
        loop_layers[name + 'act'] = LeakyReLU(alpha=.1, name=name + 'act') if (act == 'leakyrelu') else Activation(act, name=name + 'act')
        offsets.append(loop_layers[name + 'act'](offsets[-1]))
        
        # offset -> significance connection
#        if connection_freq > 0:
#            if ((j+1) % connection_freq == 0) and (j+1 < layers_no):    
#                sigs.append(merge([offsets[-1], sigs[-1]], mode='concat', concat_axis=-1, name='concat' + str(j+1)))
            
    value_output = merge([offsets[-1], value_input], mode='sum', concat_axis=-1, name='value_output')

    value = Permute((2,1))(value_output)

    sig = Permute((2,1))(sigs[-1])
#    sig = TimeDistributed(Dense(input_length, activation='softmax'), name='softmax')(sig) ## SHOULD BE UNNECESSARY, GAVE GOOD RESULTS. SIMILAR PERFORMANCE WITHOUT.
    if architecture['softmax']:    
        sig = TimeDistributed(Activation('softmax'), name='softmax')(sig)
    elif architecture['lambda']:    
        sig = TimeDistributed(Activation('softplus'), name='relulambda')(sig)
        sig = TimeDistributed(Lambda(lambda x: x/K.sum(x, axis=-1, keepdims=True)), name='lambda')(sig)
        
    main = merge([sig, value], mode='mul', concat_axis=-1, name='significancemerge')
    if shared_final_weights:
        out = TimeDistributed(Dense(output_length, activation='linear', bias=False,
                                    W_constraint=nonneg() if nonnegative else None),
                              name= 'out')(main)
    else: 
        out = LocallyConnected1D(nb_filter=1, filter_length=1,   # dimensions permuted. time dimension treated as separate channels, no connections between different features
                                 border_mode='valid')(main)
        
    main_output = Permute((2,1), name='main_output')(out)
    
    nn = Model(input=[inp, value_input], output=[main_output, value_output])
    
    nn.compile(optimizer=keras.optimizers.Adam(lr=.001),
               loss={'main_output': 'mse', 'value_output' : 'mse'},
               loss_weights={'main_output': 1., 'value_output': aux_weight}) 

    train_gen = G.gen('train', func=regr_func)
    valid_gen = G.gen('valid', func=regr_func)
    reducer = LrReducer(patience=patience, reduce_rate=.1, reduce_nb=3, 
                        verbose=1, monitor='val_main_output_loss', restore_best=True)
    
    print('Total model parameters: %d' % int(np.sum([np.sum([np.prod(K.eval(w).shape) for w in l.trainable_weights]) for l in nn.layers])))
    
    length = input_length + output_length
    hist = nn.fit_generator(
        train_gen,
        samples_per_epoch = G.n_train - length,
        nb_epoch=1000,
        callbacks=[reducer],
    #            callbacks=[callback, keras.callbacks.EarlyStopping(monitor='val_loss', patience=patience)],
        validation_data=valid_gen,
        nb_val_samples=G.n_all - G.n_train - length,
        verbose=verbose
    )    
    return hist, nn, reducer
    
    

def CNNmodel(datasource, params):
    globals().update(params)
    G = generator(filename=datasource, train_share=train_share,
            input_length=input_length, 
            output_length=output_length, verbose=verbose,
            batch_size=batch_size, diffs=diffs)
    
    dim = G.get_dim()
    cols = G.get_target_cols()
    regr_func = G.make_io_func(io_form='regression', cols=target_cols)

    # theano.config.compute_test_value = 'off'
    # valu.tag.test_value
    inp = Input(shape=(input_length, dim), dtype='float32', name='value_input')

    outs = [inp]
    loop_layers = {}
    
    for j in range(layers_no):
        if (maxpooling > 0) and ((j + 1) % maxpooling == 0):
            loop_layers['maxpool' + str(j+1)] = MaxPooling1D(pool_length=poolsize,
                                                             border_mode='valid')
            outs.append(loop_layers['maxpool' + str(j+1)](outs[-1]))
        else:    
            name = 'conv' + str(j+1)
            ks = kernelsize[j % len(kernelsize)] if (type(kernelsize) == list) else kernelsize
            loop_layers[name] = Convolution1D(filters if (j < layers_no - 1) else len(cols), 
                                              filter_length=ks, border_mode='same', 
                                              activation='linear', name=name,
                                              W_constraint=maxnorm(norm))
            outs.append(loop_layers[name](outs[-1]))
            
            loop_layers[name + 'BN'] = BatchNormalization(name=name + 'BN')
            outs.append(loop_layers[name + 'BN'](outs[-1]))
            
            # residual connections
            if resnet and (maxpooling > 0) and (j > 0) and (j % maxpooling == 0):
                outs.append(merge([outs[-1], outs[-3 * (maxpooling - 1)]], mode='sum', 
                                  concat_axis=-1, name='residual' + str(j+1)))
                
            loop_layers[name + 'act'] = LeakyReLU(alpha=.1, name=name + 'act') if (act == 'leakyrelu') else Activation(act, name=name + 'act')
            outs.append(loop_layers[name + 'act'](outs[-1]))
            
            
#    mp5 = Dropout(dropout)(mp5)
    flat = Flatten()(outs[-1])
    out = Dense(len(cols) * output_length, activation='linear', W_constraint=maxnorm(100))(flat)  
    
    nn = Model(input=inp, output=out)
    
    nn.compile(optimizer=keras.optimizers.Adam(lr=.001),
               loss='mse') 

    train_gen = G.gen('train', func=regr_func)
    valid_gen = G.gen('valid', func=regr_func)
    reducer = LrReducer(patience=patience, reduce_rate=.1, reduce_nb=3, verbose=1, monitor='val_loss', restore_best=True)
    
    print('Total model parameters: %d' % int(np.sum([np.sum([np.prod(K.eval(w).shape) for w in l.trainable_weights]) for l in nn.layers])))
    
    length = input_length + output_length
    hist = nn.fit_generator(
        train_gen,
        samples_per_epoch = G.n_train - length,
        nb_epoch=1000,
        callbacks=[reducer],
    #            callbacks=[callback, keras.callbacks.EarlyStopping(monitor='val_loss', patience=patience)],
        validation_data=valid_gen,
        nb_val_samples=G.n_all - G.n_train - length,
        verbose=verbose
    )    
    return hist, nn, reducer


    
def LSTMmodel(datasource, params):
    globals().update(params)
    G = generator(filename=datasource, train_share=train_share,
            input_length=input_length, 
            output_length=output_length, verbose=verbose,
            batch_size=batch_size, diffs=diffs)
    
    dim = G.get_dim()
    cols = G.get_target_cols()
    regr_func = G.make_io_func(io_form='regression', cols=target_cols)

    # theano.config.compute_test_value = 'off'
    # valu.tag.test_value
    nn = Sequential()
    
    if dropout > 0:
        nn.add(Dropout(dropout, name='dropout'))
    nn.add(LSTM(layer_size,
                batch_input_shape=(batch_size, input_length, dim),
                stateful=True, activation=None,
                inner_activation='sigmoid', name='lstm',
                return_sequences=True))
    if act == 'leakyrelu':
        nn.add(LeakyReLU(alpha=.1, name='lstm_act'))
    else:
        nn.add(Activation(act, name='lstm_act'))
    nn.add(TimeDistributed(Dense(len(cols), W_constraint=maxnorm(norm)), name='tddense'))
    nn.add(Reshape((input_length*len(cols),)))
    
    nn.compile(optimizer=keras.optimizers.Adam(lr=.001, clipnorm=1.),
               loss='mse') 

    train_gen = G.gen('train', func=regr_func, shuffle=False)
    valid_gen = G.gen('valid', func=regr_func, shuffle=False)
    reducer = LrReducer(patience=patience, reduce_rate=.1, reduce_nb=3, verbose=1, 
                        monitor='val_loss', restore_best=True, reset_states=True)
    
    print('Total model parameters: %d' % int(np.sum([np.sum([np.prod(K.eval(w).shape) for w in l.trainable_weights]) for l in nn.layers])))
    
    hist = nn.fit_generator(
        train_gen,
        samples_per_epoch = G.n_train - G.l,
        nb_epoch=1000,
        callbacks=[reducer],
    #            callbacks=[callback, keras.callbacks.EarlyStopping(monitor='val_loss', patience=patience)],
        validation_data=valid_gen,
        nb_val_samples=G.n_all - G.n_train,
        verbose=verbose
    )    
    return hist, nn, reducer