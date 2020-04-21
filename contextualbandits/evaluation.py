# -*- coding: utf-8 -*-

import pandas as pd, numpy as np
from .utils import _check_fit_input, _check_1d_inp, \
        _check_X_input, _check_random_state
from .online import SeparateClassifiers

def evaluateRejectionSampling(policy, X, a, r, online=True, partial_fit=False,
                              start_point_online='random', random_state=1,
                              update_freq=10):
    """
    Evaluate a policy using rejection sampling on test data.
    
    Note
    ----
    In order for this method to be unbiased, the actions on the test sample must have been
    collected at random and not according to some other policy.
    
    Parameters
    ----------
    policy : obj
        Policy to be evaluated (already fitted to data). Must have a 'predict' method.
        If it is an online policy, it must also have a 'fit' method.
    X : array (n_samples, n_features)
        Matrix of covariates for the available data.
    a : array (n_samples), int type
        Arms or actions that were chosen for each observation.
    r : array (n_samples), {0,1}
        Rewards that were observed for the chosen actions. Must be binary rewards 0/1.
    online : bool
        Whether this is an online policy to be evaluated by refitting it to the data
        as it makes choices on it.
    partial_fit : bool
        Whether to use 'partial_fit' when fitting the policy to more data.
        Ignored if passing ``online=False``.
    start_point_online : either str 'random' or int in [0, n_samples-1]
        Point at which to start evaluating cases in the sample.
        Only used when passing online=True.
    random_state : int, None, or RandomState
        Either an integer which will be used as seed for initializing a
        ``RandomState`` object for random number generation, or a ``RandomState``
        object (from NumPy), which will be used directly. This is only used when
        passing ``start_point_online='random'``.
    update_freq : int
        After how many rounds to refit the policy being evaluated.
        Only used when passing ``online=True``.
        
    Returns
    -------
    result : tuple (float, int)
        Estimated mean reward and number of observations taken.
        
    References
    ----------
    .. [1] Li, Lihong, et al. "A contextual-bandit approach to personalized news article recommendation."
           Proceedings of the 19th international conference on World wide web. ACM, 2010.
    """
    X,a,r=_check_fit_input(X,a,r)
    if start_point_online=='random':
        random_state = _check_random_state(random_state)
        start_point_online = random_state.integers(X.shape[0])
    else:
        if isinstance(start_point_online, int):
            pass
        elif isinstance(start_point_online, float):
            pass
        else:
            raise ValueError("'start_point_online' must be one of 'random', float [0,1] or int [0, sample_size]")
    
    if not online:
        pred=policy.predict(X)
        match=pred==a
        return (np.mean(r[match]), match.sum())
    else:
        ### TODO: this for loop approach is too slow, should instead have a
        ### forward window to make predictions in batches and then backtrack
        ### at the time a refit is due.
        cum_r=0
        cum_n=0
        ix_chosen=list()
        policy.fit(X[:0], a[:0], r[:0])
        for i in range(start_point_online, X.shape[0]):
            obs=X[i].reshape((1,-1))
            would_choose=policy.predict(obs)[0]
            if would_choose==a[i]:
                cum_r+=r[i]
                cum_n+=1
                ix_chosen.append(i)
                if (cum_n%update_freq)==0:
                    if not partial_fit:
                        ix_fit=np.array(ix_chosen)
                        policy.fit(X[ix_fit], a[ix_fit], r[ix_fit])
                    else:
                        ix_fit = np.array(ix_chosen[:-(update_freq+1):-1])
                        policy.partial_fit(X[ix_fit], a[ix_fit], r[ix_fit])
        for i in range(0, start_point_online):
            obs=X[i].reshape(1,-1)
            would_choose=policy.predict(obs)[0]
            if would_choose==a[i]:
                cum_r+=r[i]
                cum_n+=1
                ix_chosen.append(i)
                if (cum_n%update_freq)==0:
                    if not partial_fit:
                        ix_fit=np.array(ix_chosen)
                        policy.fit(X[ix_fit], a[ix_fit], r[ix_fit])
                    else:
                        ix_fit = np.array(ix_chosen)[:-(update_freq+1):-1]
                        policy.partial_fit(X[ix_fit], a[ix_fit], r[ix_fit])
        if cum_n==0:
            raise ValueError("Rejection sampling couldn't obtain any matching samples.")
        return (cum_r/cum_n, cum_n)
    

def evaluateDoublyRobust(pred, X, a, r, p, reward_estimator, nchoices=None,
                         handle_invalid=True, c=None, pmin=1e-5,
                         random_state = 1):
    """
    Doubly-Robust Policy Evaluation
    
    Evaluates rewards of arm choices of a policy from data collected by another policy, using a reward estimator along with the historical probabilities
    (hence the name).
    
    Note
    ----
    This method requires to form reward estimates of the arms that were chosen and of the arms
    that the policy to be evaluated would choose. In order to do so, you can either provide
    estimates as an array (see Parameters), or pass a model.
    
    One method to obtain reward estimates is to fit a model to both the training and test data
    and use its predictions as reward estimates. You can do so by passing an object of class
    `contextualbandits.online.SeparateClassifiers` which should be already fitted.
    
    Another method is to fit a model to the test data, in which case you can pass a classifier
    with a 'predict_proba' method here, which will be fit to the same test data passed to this
    function to obtain reward estimates.
    
    The last two options can suffer from invalid predictions if there are some arms for which every time
    they were chosen they resulted in a reward, or never resulted in a reward. In such cases,
    this function includes the option to impute the "predictions" for them (which would otherwise
    always be exactly zero or one regardless of the context) by replacing them with random
    numbers ~Beta(3,1) or ~Beta(1,3) for the cases of always good and always bad.
    
    This is just a wild idea though, and doesn't guarantee reasonable results in such siutation.
    
    Note that, if you are using the 'SeparateClassifiers' class from the online module in this
    same package, it comes with a method 'predict_proba_separate' that can be used to get reward
    estimates. It still can suffer from the same problem of always-one and always-zero predictions though.
    
    Parameters
    ----------
    pred : array (n_samples,)
        Arms that would be chosen by the policy to evaluate.
    X : array (n_samples, n_features)
        Matrix of covariates for the available data.
    a : array (n_samples), int type
        Arms or actions that were chosen for each observation.
    r : array (n_samples), {0,1}
        Rewards that were observed for the chosen actions. Must be binary rewards 0/1.
    p : array (n_samples)
        Scores or reward estimates from the policy that generated the data for the actions
        that were chosen by it.
    reward_estimator : obj or array (n_samples, 2)
        One of the following:
            * An array with the first column corresponding to the reward estimates for the action chosen
              by the new policy, and the second column corresponding to the reward estimates for the
              action chosen in the data (see Note for details).
            * An already-fit object of class 'contextualbandits.online.SeparateClassifiers', which will
              be used to make predictions on the actions chosen and the actions that the new
              policy would choose.
            * A classifier with a 'predict_proba' method, which will be fit to the same test data
              passed here in order to obtain reward estimates (see Note for details).
    nchoices : int
        Number of arms/labels to choose from.
        Only used when passing a classifier object to 'reward_estimator'.
    handle_invalid : bool
        Whether to replace 0/1 estimated rewards with randomly-generated numbers (see Note)
    c : None or float
        Constant by which to multiply all scores from the exploration policy.
    pmin : None or float
        Scores (from the exploration policy) will be converted to the minimum between
        pmin and the original estimate.
    random_state : int, None, or RandomState
        Either an integer which will be used as seed for initializing a
        ``RandomState`` object for random number generation, or a ``RandomState``
        object (from NumPy), which will be used directly.

    Returns
    -------
    est : float
        The estimated mean reward that the new policy would obtain on the 'X' data.
    
    References
    ----------
    .. [1] Dudík, Miroslav, John Langford, and Lihong Li. "Doubly robust policy evaluation and learning."
           arXiv preprint arXiv:1103.4601 (2011).
    """
    X,a,r=_check_fit_input(X,a,r)
    p=_check_1d_inp(p)
    pred=_check_1d_inp(pred)
    assert p.shape[0]==X.shape[0]
    assert pred.shape[0]==X.shape[0]
    if c is not None:
        assert isinstance(c, float)
    if pmin is not None:
        assert isinstance(pmin, float)

    rs = _check_random_state(random_state)
    
    if type(reward_estimator)==np.ndarray:
        assert reward_estimator.shape[1]==2
        assert reward_estimator.shape[0]==X.shape[0]
        rhat_new = reward_estimator[:, 0]
        rhat_old = reward_estimator[:, 1]
    elif 'predict_proba_separate' in dir(reward_estimator):
        rhat = reward_estimator.predict_proba_separate(X)
        rhat_new = rhat[np.arange(rhat.shape[0]), pred]
        rhat_old = rhat[np.arange(rhat.shape[0]), a]
    elif 'predict_proba' in dir(reward_estimator):
        reward_estimator = SeparateClassifiers(reward_estimator, nchoices, random_state=rs)
        reward_estimator.fit(X, a, r)
        rhat = reward_estimator.predict_proba_separate(X)
        rhat_new = rhat[np.arange(rhat.shape[0]), pred]
        rhat_old = rhat[np.arange(rhat.shape[0]), a]
    else:
        error_msg = "'reward_estimator' must be either an array, a classifier with"
        error_msg += "'predict_proba', or a 'SeparateClassifiers' object."
        raise ValueError(error_msg)
    
    if handle_invalid:
        rhat_new[rhat_new==1] = rs.beta(3,1,size=rhat_new.shape)[rhat_new==1]
        rhat_new[rhat_new==0] = rs.beta(1,3,size=rhat_new.shape)[rhat_new==0]
        rhat_old[rhat_old==1] = rs.beta(3,1,size=rhat_old.shape)[rhat_old==1]
        rhat_old[rhat_old==0] = rs.beta(1,3,size=rhat_old.shape)[rhat_old==0]
    
    if c is not None:
        p = c*p
    if pmin is not None:
        p = np.clip(p, a_min=pmin, a_max=None)
    
    actions_matching = pred==a
    out = rhat_new
    out[actions_matching] += (r[actions_matching]-rhat_old[actions_matching])/p[actions_matching].reshape(-1)
    
    return np.mean(out)

def evaluateFullyLabeled(policy, X, y_onehot, online=False, shuffle=True,
                         update_freq=50, random_state=1):
    """
    Evaluates a policy on fully-labeled data
    
    Parameters
    ----------
    policy : obj
        Policy to be evaluated (already fitted to data). Must have a 'predict' method.
        If it is an online policy, it must also have a 'fit' method.
    X : array (n_samples, n_features)
        Covariates for each observation.
    y_onehot : array (n_samples, n_arms)
        Labels (zero or one) for each class for each observation.
    online : bool
        Whether the algorithm should be fit to batches of data with a 'partial_fit' method,
        or to all historical data each time.
    shuffle : bool
        Whether to shuffle the data (X and y_onehot) before passing through it.
        Be awarethat data is shuffled in-place.
    update_freq : int
        Batch size - how many observations to predict before refitting the model.
    random_state : int, None, or RandomState
        Either an integer which will be used as seed for initializing a
        ``RandomState`` object for random number generation, or a ``RandomState``
        object (from NumPy), which will be used directly. This is used when shuffling
        and when selecting actions at random for first batch.
    
    Returns
    -------
    mean_rew : array (n_samples,)
        Mean reward obtained at each batch.
    """
    if type(X).__name__=='DataFrame':
        X=X.as_matrix()
    if type(y_onehot).__name__=='DataFrame':
        y_onehot=y_onehot.as_matrix()
    
    assert type(X).__name__=='ndarray'
    assert type(y_onehot).__name__=='ndarray'
    assert isinstance(online, bool)
    assert isinstance(shuffle, bool)
    assert isinstance(update_freq, bool)
    assert X.shape[0]>update_freq
    assert X.shape[0]==y_onehot.shape[0]
    assert X.shape[0]>0

    rs = _check_random_state(random_state)
    
    if shuffle:
        new_order=np.arange(X.shape[0])
        rs.shuffle(new_order)
        X=X[new_order,:]
        y_onehot=y_onehot[new_order,:]
        
    rewards_per_turn = list()
    history_actions = np.array([])
    n_choices = y_onehot.shape[1]
    
    ## initial seed
    batch_features = X[:update_freq,:]
    batch_actions = rs.integers(y_onehot.shape[1], size=update_freq)
    batch_rewards = y_onehot[np.arange(update_freq), batch_actions]
    
    if online:
        policy.partial_fit(batch_features, batch_actions, batch_rewards)
    else:
        policy.fit(batch_features, batch_actions, batch_rewards)
        
    ## running the loop
    for i in range(int(np.floor(features.shape[0]/batch_size))):
        st=(i+1)*batch_size
        end=(i+2)*batch_size
        end=np.min([end, X.shape[0]])
        
        batch_features = X[st:end,:]
        batch_actions = policy.predict(batch_features)
        batch_rewards = y_onehot[np.arange(st, end), batch_actions]
        
        rewards_per_turn.append(rewards_per_turn.sum())
        
        if online:
            policy.partial_fit(batch_features, batch_actions, batch_rewards)
        else:
            history_actions = np.append(history_actions, batch_actions)
            policy.fit(X[:end,:], history_actions, y_onehot[np.arange(end), history_actions])
            
    ## outputting results
    def get_mean_reward(reward_lst, batch_size):
        mean_rew=list()
        for r in range(len(reward_lst)):
            mean_rew.append(sum(reward_lst[:r+1])/((r+1)*batch_size))
        return mean_rew
    
    return np.array(get_mean_reward(rewards_per_turn, update_freq))

def evaluateDoublyRobustSimplified(est, X, r, p, cmin=1e-8, cmax=1e2):
    """
    Doubly-Robust Policy Evaluation (simplified version)

    Evaluates rewards of arm choices of a policy from data collected by another policy,
    making corrections according to the estimated rewards and to the difference between
    the estimations of the new and old policy over the actions that were chosen.

    Note
    ----
    This implementation is theoretically incorrect as this whole library
    doesn't follow the paradigm of producing probabilities of choosing actions
    (it is theoretically possible for many of the methods in the ``online``
    section, but computationally inefficient and not supported by the library).
    Instead, it uses estimated expected rewards (that is, the rows of the estimations
    don't sum to 1), which is not what this method expects, but nevertheless, the
    ratio of these estimations between the old and new policy should be highly related
    to the ratio of the probabilities of choosing those actions, and as such, this
    function is likely to still produce an improvement over a naive average of the
    expected rewards across actions that were chosen by a different policy.

    Note
    ----
    Unlike the other functions in this module, function doesn't take the indices
    of the chosen actions, but rather takes the predictions directly (see the
    'Parameters' section for details). Compared to the other doubly-robust evaluation
    function, this one will not make use of the full outputs from the reward
    estimator.

    Note
    ----
    This implementation mixes the estimated rewards for the actions and the
    scores from the old policy. Usually these are the same, but in some situations
    you might dispose of a better reward estimator, in which case you might not
    want to use this function.

    Note
    ----
    The outputs of this function are not guaranteed to be bounded between zero and one.

    Parameters
    ----------
    est : array (n_samples,)
        Scores or reward estimates from the policy being evaluated on the actions
        that were chosen by the old policy for each row of 'X'.
    X : array (n_samples, n_features)
        Matrix of covariates for the available data.
    r : array (n_samples), {0,1}
        Rewards that were observed for the chosen actions.
    p : array (n_samples)
        Scores or reward estimates from the policy that generated the data for the actions
        that were chosen by it. Must be in the same scale as 'est'.
    cmin : float
        Minimum value for the ratio between estimations to assign to observations.
        If any ratio is below this number, it will be assigned this value (i.e.
        will be clipped).
    cmax : float
        Maximum value of the ratio between estimations that will be taken.
        Observations with ratios higher than this will be discarded rather
        than clipped.

    Returns
    -------
    est : float
        The estimated mean reward that the new policy would obtain on the 'X' data.

    References
    ----------
    .. [1] Gilotte, Alexandre, et al.
           "Offline a/b testing for recommender systems."
           Proceedings of the Eleventh ACM International Conference on Web Search and Data Mining. 2018.
    """
    est = _check_1d_inp(est)
    p = _check_1d_inp(p)
    assert est.shape[0] == X.shape[0]
    assert p.shape[0] == X.shape[0]
    X, _, r=_check_fit_input(X, np.zeros(p.shape[0]), r)

    w = np.clip(est / p, a_min=cmin, a_max=None)
    take = w <= cmax
    if np.sum(take) == 0:
        raise ValueError("No cases below maximum 'c'.")
    return np.mean((r[take] - p[take]) * w[take] + est[take])

def evaluateNCIS(est, X, r, p, cmin=1e-8, cmax=1e3):
    """
    Normalized Capped Importance Sampling

    Evaluates rewards of arm choices of a policy from data collected by another policy,
    making corrections according to the difference between the estimations of the
    new and old policy over the actions that were chosen.

    Note
    ----
    This implementation is theoretically incorrect as this whole library
    doesn't follow the paradigm of producing probabilities of choosing actions
    (it is theoretically possible for many of the methods in the ``online``
    section, but computationally inefficient and not supported by the library).
    Instead, it uses estimated expected rewards (that is, the rows of the estimations
    don't sum to 1), which is not what this method expects, but nevertheless, the
    ratio of these estimations between the old and new policy should be highly related
    to the ratio of the probabilities of choosing those actions, and as such, this
    function is likely to still produce an improvement over a naive average of the
    expected rewards across actions that were chosen by a different policy.

    Note
    ----
    Unlike the other functions in this module, function doesn't take the indices
    of the chosen actions, but rather takes the predictions directly (see the
    'Parameters' section for details).

    Parameters
    ----------
    est : array (n_samples,)
        Scores or reward estimates from the policy being evaluated on the actions
        that were chosen by the old policy for each row of 'X'.
    X : array (n_samples, n_features)
        Matrix of covariates for the available data.
    r : array (n_samples), {0,1}
        Rewards that were observed for the chosen actions.
    p : array (n_samples)
        Scores or reward estimates from the policy that generated the data for the actions
        that were chosen by it. Must be in the same scale as 'est'.
    cmin : float
        Minimum value for the ratio between estimations to assign to observations.
        If any ratio is below this number, it will be assigned this value (i.e.
        will be clipped).
    cmax : float
        Maximum value of the ratio between estimations that will be taken.
        Observations with ratios higher than this will be discarded rather
        than clipped.

    Returns
    -------
    est : float
        The estimated mean reward that the new policy would obtain on the 'X' data.
    
    References
    ----------
    .. [1] Gilotte, Alexandre, et al.
           "Offline a/b testing for recommender systems."
           Proceedings of the Eleventh ACM International Conference on Web Search and Data Mining. 2018.
    """
    est = _check_1d_inp(est)
    p = _check_1d_inp(p)
    assert est.shape[0] == X.shape[0]
    assert p.shape[0] == X.shape[0]
    X, _, r=_check_fit_input(X, np.zeros(p.shape[0]), r)

    w = np.clip(est / p, a_min=cmin, a_max=None)
    take = w <= cmax
    if np.sum(take) == 0:
        raise ValueError("No cases below maximum 'c'.")
    return np.einsum("ij,ij->i", w[take], r[take]) / np.sum(w[take])
