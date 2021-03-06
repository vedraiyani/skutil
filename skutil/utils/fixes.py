# -*- coding: utf-8 -*-
"""
The purpose of the utils.fixes module is to provide
fixes to non version-invariant methods or behavior.
We want to perform as view version-specific checks
as possible, so anything that requires version-specific
behavior should be placed in fixes.
Author: Taylor G Smith
"""

from __future__ import division, absolute_import, print_function
import numbers
import numpy as np
import pandas as pd
import sklearn
import sys
from abc import ABCMeta, abstractmethod
from sklearn.base import BaseEstimator, MetaEstimatorMixin, is_classifier, clone
from sklearn.externals import six
from sklearn.externals.joblib import Parallel, delayed
from sklearn.utils.validation import _num_samples, check_is_fitted, check_consistent_length #,indexable
from sklearn.metrics.scorer import check_scoring
from collections import namedtuple, Sized
from .metaestimators import if_delegate_has_method
import warnings

__all__ = [
    'dict_keys',
    'dict_values',
    'is_iterable'
]

VERSION_MAJOR = sys.version_info.major
NoneType = type(None)  # Python 3 doesn't have a types.NoneType

# easier test for numericism
if VERSION_MAJOR > 2:
    long = int

# grid_search deprecation in sklearn 0.18
if sklearn.__version__ >= '0.18':
    SK18 = True
    from sklearn.model_selection import check_cv
    from sklearn.model_selection._validation import _fit_and_score
    from sklearn.model_selection import ParameterSampler, ParameterGrid


    def _do_fit(n_jobs, verbose, pre_dispatch, base_estimator,
                X, y, scorer, parameter_iterable, fit_params,
                error_score, cv, **kwargs):
        groups = kwargs.pop('groups')

        # test_score, n_samples, parameters
        out = Parallel(n_jobs=n_jobs, verbose=verbose, pre_dispatch=pre_dispatch)(
            delayed(_fit_and_score)(
                clone(base_estimator), X, y, scorer,
                train, test, verbose, parameters,
                fit_params=fit_params,
                return_train_score=False,
                return_n_test_samples=True,
                return_times=False,
                return_parameters=True,
                error_score=error_score)
            for parameters in parameter_iterable
            for train, test in cv.split(X, y, groups))

        # test_score, n_samples, _, parameters
        return [(mod[0], mod[1], None, mod[2]) for mod in out]


else:
    SK18 = False
    # catch deprecation warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        from sklearn.cross_validation import check_cv
        from sklearn.cross_validation import _fit_and_score
        from sklearn.grid_search import ParameterSampler, ParameterGrid


    def _do_fit(n_jobs, verbose, pre_dispatch, base_estimator,
                X, y, scorer, parameter_iterable, fit_params,
                error_score, cv, **kwargs):
        # test_score, n_samples, score_time, parameters
        return Parallel(n_jobs=n_jobs, verbose=verbose, pre_dispatch=pre_dispatch)(
            delayed(_fit_and_score)(
                clone(base_estimator), X, y, scorer,
                train, test, verbose, parameters,
                fit_params, return_parameters=True,
                error_score=error_score)
            for parameters in parameter_iterable
            for train, test in cv)


def dict_keys(d):
    """In python 3, the ``d.keys()`` method
    returns a view and not an actual list.

    Parameters
    ----------

    d : dict
        The dictionary


    Returns
    -------

    list
    """
    return list(d.keys())


def dict_values(d):
    """In python 3, the ``d.values()`` method
    returns a view and not an actual list.

    Parameters
    ----------

    d : dict
        The dictionary


    Returns
    -------

    list
    """
    return list(d.values())


def is_iterable(x):
    """Python 3.x adds the ``__iter__`` attribute
    to strings. Thus, our previous tests for iterable
    will fail when using ``hasattr``.

    Parameters
    ----------

    x : object
        The object or primitive to test whether
        or not is an iterable.


    Returns
    -------

    bool
        True if ``x`` is an iterable
    """
    if isinstance(x, six.string_types):
        return False
    return hasattr(x, '__iter__')


def _cols_if_none(X, self_cols):
    """Since numerous transformers in the preprocessing
    and feature selection modules take ``cols`` arguments
    (which could end up as ``None`` via the ``validate_is_pd``
    method), this will return the columns that should be used.

    Parameters
    ----------

    X : Pandas ``DataFrame``
        The data frame being transformed.

    self_cols : list (string) or None
        The columns.
    """
    return X.columns.tolist() if not self_cols else self_cols


def _is_integer(x):
    """Determine whether some object ``x`` is an
    integer type (int, long, etc). This is part of the 
    ``fixes`` module, since Python 3 removes the long
    datatype, we have to check the version major.

    Parameters
    ----------

    x : object
        The item to assess whether is an integer.


    Returns
    -------

    bool
        True if ``x`` is an integer type
    """
    return (not isinstance(x, (bool, np.bool))) and \
        isinstance(x, (numbers.Integral, int, np.int, np.long, long))  # no long type in python 3


def _grid_detail(search, z_score, sort_results=True, sort_by='mean_test_score', ascending=True):
    """Create a dataframe of grid search details for either sklearn 0.17,
    sklearn 0.18 or a BaseH2OSearchCV instance.

    Parameters
    ----------

    search : sklearn 0.17 grid search
        The already fitted grid search.

    z_score : float
        The z-score by which to multiply the cross validation
        score standard deviations.

    sort_results : bool, optional (default=True)
        Whether to sort the results based on score

    sort_by : str, optional (default='mean_test_score')
        The column to sort by. This is not validated, in case
        the user wants to sort by a parameter column. If
        not ``sort_results``, this is unused.

    ascending : bool, optional (default=True)
        If ``sort_results`` is True, whether to use asc or desc
        in the sorting process.


    Returns
    -------
    
    result_df : pd.DataFrame, shape=(n_iter, n_params)
        The results of the grid search
    """
    check_is_fitted(search, 'best_estimator_')

    if not hasattr(search, 'cv_results_'):
        # if it has the grid_scores_ attribute, it's either
        # sklearn 0.17 or it's an H2O grid search. This should handle
        # both cases.

        # list of dicts
        df_list = []

        # convert each score tuple into dicts
        for score in search.grid_scores_:
            results_dict = dict(score.parameters)  # the parameter tuple or sampler
            results_dict["mean_test_score"] = score.mean_validation_score
            results_dict["std_test_score"] = score.cv_validation_scores.std() * z_score
            df_list.append(results_dict)

        # make into a data frame
        result_df = pd.DataFrame(df_list)
        drops = ['mean_test_score', 'std_test_score']

    else:
        # sklearn made this a bit easier for our purposes... kinda
        result_df = pd.DataFrame(search.cv_results_)

        # pop off the splitX cols
        result_df.drop([x for x in result_df.columns if x.startswith('split')], axis=1, inplace=True)
        result_df.drop(['rank_test_score', 'params'], axis=1, inplace=True)

        # cols that start with param should not.
        new_cols = [x if not x.startswith('param_') else x[6:] for x in result_df.columns]
        result_df.columns = new_cols

        # adjust by z-score
        for col in result_df.columns:
            if col in ('std_test_score', 'std_train_score', 'std_score_time', 'std_fit_time'):
                result_df[col] = result_df[col] * z_score

        # assign drops
        drops = ('mean_fit_time', 'mean_score_time', 
                 'mean_train_score', 'std_fit_time', 
                 'std_score_time', 'std_train_score',
                 'mean_test_score', 'std_test_score')

    # sort if necessary
    if sort_results:
        result_df = result_df.sort_values(sort_by, ascending=ascending)

    # return
    return result_df, drops


def _cv_len(cv, X, y):
    """This method computes the length of a cross validation
    object, agnostic of whether sklearn-0.17 or sklearn-0.18
    is being used.

    Parameters
    ----------

    cv : `sklearn.cross_validation._PartitionIterator` or `sklearn.model_selection.BaseCrossValidator`
        The cv object from which to extract length. If using
        sklearn-0.17, this can be computed by calling `len` on
        ``cv``, else it's computed with `cv.get_n_splits(X, y)`.

    X : pd.DataFrame or np.ndarray, shape(n_samples, n_features)
        The dataframe or np.ndarray being fit in the grid search.

    y : np.ndarray, shape(n_samples,)
        The target being fit in the grid search.

    Returns
    -------

    int
    """
    return len(cv) if not SK18 else cv.get_n_splits(X, y)


def _set_cv(cv, X, y, classifier):
    """This method returns either a `sklearn.cross_validation._PartitionIterator` or 
    `sklearn.model_selection.BaseCrossValidator` depending on whether sklearn-0.17
    or sklearn-0.18 is being used.

    Parameters
    ----------

    cv : int, `_PartitionIterator` or `BaseCrossValidator`
        The CV object or int to check. If an int, will be converted
        into the appropriate class of crossvalidator.

    X : pd.DataFrame or np.ndarray, shape(n_samples, n_features)
        The dataframe or np.ndarray being fit in the grid search.

    y : np.ndarray, shape(n_samples,)
        The target being fit in the grid search.

    classifier : bool
        Whether the estimator being fit is a classifier

    Returns
    -------

    `_PartitionIterator` or `BaseCrossValidator`
    """
    return check_cv(cv, X, y, classifier) if not SK18 else check_cv(cv, y, classifier)


def _get_groups(X, y):
    """Depending on whether using sklearn-0.17 or sklearn-0.18,
    groups must be computed differently. This method computes groups
    agnostic to the version of sklearn.

    Parameters
    ----------

    X : pd.DataFrame or np.ndarray, shape(n_samples, n_features)
        The dataframe or np.ndarray being fit in the grid search.

    y : np.ndarray, shape(n_samples,)
        The target being fit in the grid search.

    Returns
    -------

    groups : indexable
        The groups
    """
    if SK18:
        X, y = _indexable(X, y)
    return X, y, None


def _as_numpy(y):
    """Given a 1d array or iterable, create
    and return a np.ndarray of one-dimension.

    Parameters
    ----------

    y : np.ndarray, shape(n_samples,)
        The target being fit in the grid search.

    Returns
    -------

    np.ndarray, shape(n_samples,)
    """
    if y is None:
        return None
    elif isinstance(y, np.ndarray):
        return np.copy(y)
    elif hasattr(y, 'as_matrix'):
        return y.as_matrix()
    elif hasattr(y, 'tolist'):
        return y.tolist()
    elif is_iterable(y):
        return np.asarray([i for i in y])  # might accidentally force object type in 3
    raise TypeError('cannot convert type %s to numpy ndarray' % type(y))


def _indexable(X, y):
    """Make arrays indexable for cross-validation. Checks consistent 
    length, passes through None, and ensures that everything can be indexed.

    Parameters
    ----------

    X : array-like or pandas DataFrame, shape = [n_samples, n_features]
        Input data, where n_samples is the number of samples and
        n_features is the number of features.

    y : array-like, shape = [n_samples] or [n_samples, n_output], optional
        Target relative to X for classification or regression;
        None for unsupervised learning.
    """
    result = [_validate_X(X), _validate_y(y)]
    check_consistent_length(*result)
    return result


def _validate_X(X):
    """Returns X if X isn't a pandas frame, otherwise 
    the underlying matrix in the frame. """
    return X if not isinstance(X, pd.DataFrame) else X.as_matrix()


def _validate_y(y):
    """Returns y if y isn't a series, otherwise the array"""
    if y is None:  # unsupervised
        return y

    # if it's a series
    elif isinstance(y, pd.Series):
        return _as_numpy(y)

    # if it's a dataframe:
    elif isinstance(y, pd.DataFrame):
        # check it's X dims
        if y.shape[1] > 1:
            raise ValueError('matrix provided as y')
        return _as_numpy(y[y.columns[0]])

    elif is_iterable(y):
        return _as_numpy(y)

    # bail
    raise ValueError('Cannot create indexable from type=%s' % type(y))


def _check_param_grid(param_grid):
    if hasattr(param_grid, 'items'):
        param_grid = [param_grid]

    for p in param_grid:
        for v in p.values():
            if isinstance(v, np.ndarray) and v.ndim > 1:
                raise ValueError("Parameter array should be one-dimensional.")

            check = [isinstance(v, k) for k in (list, tuple, np.ndarray)]
            if True not in check:
                raise ValueError("Parameter values should be a list. "
                                 "Got %s" % str(param_grid))

            if len(v) == 0:
                raise ValueError("Parameter values should be a non-empty "
                                 "list.")


class _CVScoreTuple(namedtuple('_CVScoreTuple', ('parameters', 'mean_validation_score', 'cv_validation_scores'))):
    """This class is not accessible to the public via the sklearn API,
    so having to define it explicitly here for use with the grid search methods.

    A raw namedtuple is very memory efficient as it packs the attributes
    in a struct to get rid of the __dict__ of attributes in particular it
    does not copy the string for the keys on each instance.
    By deriving a namedtuple class just to introduce the __repr__ method we
    would also reintroduce the __dict__ on the instance. By telling the
    Python interpreter that this subclass uses static __slots__ instead of
    dynamic attributes. Furthermore we don't need any additional slot in the
    subclass so we set __slots__ to the empty tuple. """
    __slots__ = tuple()

    def __repr__(self):
        """Simple custom repr to summarize the main info"""
        return "mean: {0:.5f}, std: {1:.5f}, params: {2}".format(
            self.mean_validation_score,
            np.std(self.cv_validation_scores),
            self.parameters)


class _SK17BaseSearchCV(six.with_metaclass(ABCMeta, BaseEstimator,
                                           MetaEstimatorMixin)):
    """Base class for hyper parameter search with cross-validation.
    scikit-utils must redefine this class, because sklearn's version
    internally treats all Xs and ys as lists or np.ndarrays. We redefine
    to handle pandas dataframes as well.
    """

    @abstractmethod
    def __init__(self, estimator, scoring=None,
                 fit_params=None, n_jobs=1, iid=True,
                 refit=True, cv=None, verbose=0, pre_dispatch='2*n_jobs',
                 error_score='raise'):

        self.scoring = scoring
        self.estimator = estimator
        self.n_jobs = n_jobs
        self.fit_params = fit_params if fit_params is not None else {}
        self.iid = iid
        self.refit = refit
        self.cv = cv
        self.verbose = verbose
        self.pre_dispatch = pre_dispatch
        self.error_score = error_score

    @property
    def _estimator_type(self):
        return self.estimator._estimator_type

    def score(self, X, y=None):
        """Returns the score on the given data, if the estimator has been refit.
        This uses the score defined by ``scoring`` where provided, and the
        ``best_estimator_.score`` method otherwise.

        Parameters
        ----------
        X : array-like or pandas DataFrame, shape = [n_samples, n_features]
            Input data, where n_samples is the number of samples and
            n_features is the number of features.

        y : array-like, shape = [n_samples] or [n_samples, n_output], optional
            Target relative to X for classification or regression;
            None for unsupervised learning.

        Returns
        -------
        score : float

        Notes
        -----
         * The long-standing behavior of this method changed in version 0.16.
         * It no longer uses the metric provided by ``estimator.score`` if the
           ``scoring`` parameter was set when fitting.
        """
        X = _validate_X(X)
        y = _validate_y(y)

        if not hasattr(self, 'scorer_') or self.scorer_ is None:
            raise ValueError("No score function explicitly defined, "
                             "and the estimator doesn't provide one %s"
                             % self.best_estimator_)

        # we've already fit, and we have a scorer
        if self.scoring is not None and hasattr(self.best_estimator_, 'score'):
            warnings.warn("The long-standing behavior to use the estimator's "
                          "score function in {0}.score has changed. The "
                          "scoring parameter is now used."
                          "".format(self.__class__.__name__),
                          UserWarning)
        return self.scorer_(self.best_estimator_, X, y)

    @if_delegate_has_method(delegate='estimator', method='predict')
    def fit_predict(self, X, y):
        """Fit the estimator and then predict on the X matrix

        Parameters
        ----------
        X : array-like or pandas DataFrame, shape = [n_samples, n_features]
            Input data, where n_samples is the number of samples and
            n_features is the number of features.

        y : array-like, shape = [n_samples] or [n_samples, n_output], optional
            Target relative to X for classification or regression;
            None for unsupervised learning.

        """
        return self.fit(X, y).predict(X)

    @if_delegate_has_method(delegate='estimator', method='transform')
    def fit_transform(self, X, y):
        """Fit the estimator and then transform the X matrix

        Parameters
        ----------
        X : array-like or pandas DataFrame, shape = [n_samples, n_features]
            Input data, where n_samples is the number of samples and
            n_features is the number of features.

        y : array-like, shape = [n_samples] or [n_samples, n_output], optional
            Target relative to X for classification or regression;
            None for unsupervised learning.
        """
        return self.fit(X, y).transform(X)

    @if_delegate_has_method(delegate='estimator')
    def predict(self, X):
        """Call predict on the estimator with the best found parameters.
        Only available if ``refit=True`` and the underlying estimator supports
        ``predict``.

        Parameters
        ----------
        X : indexable or pd.DataFrame, length n_samples
            Must fulfill the input assumptions of the
            underlying estimator.
        """
        X = _validate_X(X)
        return self.best_estimator_.predict(X)

    @if_delegate_has_method(delegate='estimator')
    def predict_proba(self, X):
        """Call predict_proba on the estimator with the best found parameters.
        Only available if ``refit=True`` and the underlying estimator supports
        ``predict_proba``.

        Parameters
        ----------
        X : indexable or pd.DataFrame, length n_samples
            Must fulfill the input assumptions of the
            underlying estimator.
        """
        X = _validate_X(X)
        return self.best_estimator_.predict_proba(X)

    @if_delegate_has_method(delegate='estimator')
    def predict_log_proba(self, X):
        """Call predict_log_proba on the estimator with the best found parameters.
        Only available if ``refit=True`` and the underlying estimator supports
        ``predict_log_proba``.

        Parameters
        ----------
        X : indexable or pd.DataFrame, length n_samples
            Must fulfill the input assumptions of the
            underlying estimator.
        """
        X = _validate_X(X)
        return self.best_estimator_.predict_log_proba(X)

    @if_delegate_has_method(delegate='estimator')
    def decision_function(self, X):
        """Call decision_function on the estimator with the best found parameters.
        Only available if ``refit=True`` and the underlying estimator supports
        ``decision_function``.

        Parameters
        ----------
        X : indexable or pd.DataFrame, length n_samples
            Must fulfill the input assumptions of the
            underlying estimator.
        """
        X = _validate_X(X)
        return self.best_estimator_.decision_function(X)

    @if_delegate_has_method(delegate='estimator')
    def transform(self, X):
        """Call transform on the estimator with the best found parameters.
        Only available if the underlying estimator supports ``transform`` and
        ``refit=True``.

        Parameters
        ----------
        X : indexable or pd.DataFrame, length n_samples
            Must fulfill the input assumptions of the
            underlying estimator.
        """
        X = _validate_X(X)
        return self.best_estimator_.transform(X)

    @if_delegate_has_method(delegate='estimator')
    def inverse_transform(self, Xt):
        """Call inverse_transform on the estimator with the best found parameters.
        Only available if the underlying estimator implements ``inverse_transform`` and
        ``refit=True``.

        Parameters
        ----------
        Xt : indexable or pd.DataFrame, length n_samples
            Must fulfill the input assumptions of the
            underlying estimator.
        """
        Xt = _validate_X(Xt)
        return self.best_estimator_.inverse_transform(Xt)

    def _fit(self, X, y, parameter_iterable):
        """Actual fitting,  performing the search over parameters."""
        X, y = _indexable(X, y)

        # for debugging
        assert not isinstance(X, pd.DataFrame)
        assert not isinstance(y, pd.DataFrame)

        # begin sklearn code
        estimator = self.estimator
        self.scorer_ = check_scoring(self.estimator, scoring=self.scoring)

        # n_samples = _num_samples(X)  # don't need for now...
        cv = self.cv
        cv = _set_cv(cv, X, y, classifier=is_classifier(estimator))

        if self.verbose > 0:
            if isinstance(parameter_iterable, Sized):
                n_candidates = len(parameter_iterable)
                print("Fitting {0} folds for each of {1} candidates, totalling"
                      " {2} fits".format(len(cv), n_candidates,
                                         n_candidates * len(cv)))

        base_estimator = clone(self.estimator)
        pre_dispatch = self.pre_dispatch

        # get groups, add it to kwargs
        X, y, groups = _get_groups(X, y)
        kwargs = {'groups': groups}

        # test_score, n_samples, _, parameters
        out = _do_fit(self.n_jobs, self.verbose, pre_dispatch,
                      base_estimator, X, y, self.scorer_, parameter_iterable,
                      self.fit_params, self.error_score, cv, **kwargs)

        # Out is a list of triplet: score, estimator, n_test_samples
        n_fits = len(out)
        n_folds = _cv_len(cv, X, y)

        scores = list()
        grid_scores = list()
        for grid_start in range(0, n_fits, n_folds):
            n_test_samples = 0
            score = 0
            all_scores = []
            for this_score, this_n_test_samples, _, parameters in \
                    out[grid_start:grid_start + n_folds]:
                all_scores.append(this_score)
                if self.iid:
                    this_score *= this_n_test_samples
                    n_test_samples += this_n_test_samples
                score += this_score
            if self.iid:
                score /= float(n_test_samples)
            else:
                score /= float(n_folds)
            scores.append((score, parameters))

            grid_scores.append(_CVScoreTuple(
                parameters,
                score,
                np.array(all_scores)))
        # Store the computed scores
        self.grid_scores_ = grid_scores

        # Find the best parameters by comparing on the mean validation score:
        # note that `sorted` is deterministic in the way it breaks ties
        best = sorted(grid_scores, key=lambda x: x.mean_validation_score,
                      reverse=True)[0]
        self.best_params_ = best.parameters
        self.best_score_ = best.mean_validation_score

        if self.refit:
            # fit the best estimator using the entire dataset
            # clone first to work around broken estimators
            best_estimator = clone(base_estimator).set_params(
                **best.parameters)
            if y is not None:
                best_estimator.fit(X, y, **self.fit_params)
            else:
                best_estimator.fit(X, **self.fit_params)
            self.best_estimator_ = best_estimator
        return self


class _SK17GridSearchCV(_SK17BaseSearchCV):
    """Exhaustive search over specified parameter values for an estimator.
    This class is the same as sklearn's version, however it extends the skutils 
    version of BaseSearchCV which can handle indexing pandas dataframes, 
    where sklearn's does not.

    Important members are fit, predict.
    GridSearchCV implements a "fit" and a "score" method.
    It also implements "predict", "predict_proba", "decision_function",
    "transform" and "inverse_transform" if they are implemented in the
    estimator used.

    The parameters of the estimator used to apply these methods are optimized
    by cross-validated grid-search over a parameter grid.

    Parameters
    ----------
    estimator : estimator object.
        A object of that type is instantiated for each grid point.
        This is assumed to implement the scikit-learn estimator interface.
        Either estimator needs to provide a ``score`` function,
        or ``scoring`` must be passed.

    param_grid : dict or list of dictionaries
        Dictionary with parameters names (string) as keys and lists of
        parameter settings to try as values, or a list of such
        dictionaries, in which case the grids spanned by each dictionary
        in the list are explored. This enables searching over any sequence
        of parameter settings.

    scoring : string, callable or None, default=None
        A string (see model evaluation documentation) or
        a scorer callable object / function with signature
        ``scorer(estimator, X, y)``.
        If ``None``, the ``score`` method of the estimator is used.

    fit_params : dict, optional
        Parameters to pass to the fit method.

    n_jobs : int, default=1
        Number of jobs to run in parallel.
        .. versionchanged:: 0.17
           Upgraded to joblib 0.9.3.

    pre_dispatch : int, or string, optional
        Controls the number of jobs that get dispatched during parallel
        execution. Reducing this number can be useful to avoid an
        explosion of memory consumption when more jobs get dispatched
        than CPUs can process. This parameter can be:
            - None, in which case all the jobs are immediately
              created and spawned. Use this for lightweight and
              fast-running jobs, to avoid delays due to on-demand
              spawning of the jobs
            - An int, giving the exact number of total jobs that are
              spawned
            - A string, giving an expression as a function of n_jobs,
              as in '2*n_jobs'

    iid : boolean, default=True
        If True, the data is assumed to be identically distributed across
        the folds, and the loss minimized is the total loss per sample,
        and not the mean loss across the folds.

    cv : int, cross-validation generator or an iterable, optional
        Determines the cross-validation splitting strategy.
        Possible inputs for cv are:
        - None, to use the default 3-fold cross-validation,
        - integer, to specify the number of folds.
        - An object to be used as a cross-validation generator.
        - An iterable yielding train/test splits.
        For integer/None inputs, if the estimator is a classifier and ``y`` is
        either binary or multiclass, `StratifiedKFold` used. In all
        other cases, `KFold` is used.

    refit : boolean, default=True
        Refit the best estimator with the entire dataset.
        If "False", it is impossible to make predictions using
        this GridSearchCV instance after fitting.

    verbose : integer
        Controls the verbosity: the higher, the more messages.

    error_score : 'raise' (default) or numeric
        Value to assign to the score if an error occurs in estimator fitting.
        If set to 'raise', the error is raised. If a numeric value is given,
        FitFailedWarning is raised. This parameter does not affect the refit
        step, which will always raise the error.

    Examples
    --------
    >>> from sklearn import svm, grid_search, datasets
    >>> iris = datasets.load_iris()
    >>> parameters = {'kernel':('linear', 'rbf'), 'C':[1, 10]}
    >>> svr = svm.SVC()
    >>> clf = grid_search.GridSearchCV(svr, parameters)
    >>> clf.fit(iris.data, iris.target)
    ...        # doctest: +NORMALIZE_WHITESPACE +ELLIPSIS
    GridSearchCV(cv=None, error_score=...,
           estimator=SVC(C=1.0, cache_size=..., class_weight=..., coef0=...,
                         decision_function_shape=None, degree=..., gamma=...,
                         kernel='rbf', max_iter=-1, probability=False,
                         random_state=None, shrinking=True, tol=...,
                         verbose=False),
           fit_params={}, iid=..., n_jobs=1,
           param_grid=..., pre_dispatch=..., refit=...,
           scoring=..., verbose=...)

    Attributes
    ----------
    grid_scores_ : list of named tuples
        Contains scores for all parameter combinations in param_grid.
        Each entry corresponds to one parameter setting.
        Each named tuple has the attributes:
            * ``parameters``, a dict of parameter settings
            * ``mean_validation_score``, the mean score over the
              cross-validation folds
            * ``cv_validation_scores``, the list of scores for each fold

    best_estimator_ : estimator
        Estimator that was chosen by the search, i.e. estimator
        which gave highest score (or smallest loss if specified)
        on the left out data. Not available if refit=False.

    best_score_ : float
        Score of best_estimator on the left out data.

    best_params_ : dict
        Parameter setting that gave the best results on the hold out data.

    scorer_ : function
        Scorer function used on the held out data to choose the best
        parameters for the model.

    Notes
    -----
    The parameters selected are those that maximize the score of the left out
    data, unless an explicit score is passed in which case it is used instead.
    If `n_jobs` was set to a value higher than one, the data is copied for each
    point in the grid (and not `n_jobs` times). This is done for efficiency
    reasons if individual jobs take very little time, but may raise errors if
    the dataset is large and not enough memory is available.  A workaround in
    this case is to set `pre_dispatch`. Then, the memory is copied only
    `pre_dispatch` many times. A reasonable value for `pre_dispatch` is `2 *
    n_jobs`.

    See Also
    --------
    `ParameterGrid`:
        generates all the combinations of a hyperparameter grid.

    `sklearn.cross_validation.train_test_split`:
        utility function to split the data into a development set usable
        for fitting a GridSearchCV instance and an evaluation set for
        its final evaluation.

    `sklearn.metrics.make_scorer`:
        Make a scorer from a performance metric or loss function.
    """

    def __init__(self, estimator, param_grid, scoring=None, fit_params=None,
                 n_jobs=1, iid=True, refit=True, cv=None, verbose=0,
                 pre_dispatch='2*n_jobs', error_score='raise'):
        super(_SK17GridSearchCV, self).__init__(
            estimator, scoring, fit_params, n_jobs, iid,
            refit, cv, verbose, pre_dispatch, error_score)

        self.param_grid = param_grid
        _check_param_grid(param_grid)

    def fit(self, X, y=None):
        """Run fit with all sets of parameters.

        Parameters
        ----------
        X : array-like, shape = [n_samples, n_features]
            Training vector, where n_samples is the number of samples and
            n_features is the number of features.
        y : array-like, shape = [n_samples] or [n_samples, n_output], optional
            Target relative to X for classification or regression;
            None for unsupervised learning.
        """
        return self._fit(X, y, ParameterGrid(self.param_grid))


class _SK17RandomizedSearchCV(_SK17BaseSearchCV):
    """Randomized search on hyper parameters. This class is the same as sklearn's
    version, however it extends the skutils version of BaseSearchCV which can handle
    indexing pandas dataframes, where sklearn's does not.

    RandomizedSearchCV implements a "fit" and a "score" method.
    It also implements "predict", "predict_proba", "decision_function",
    "transform" and "inverse_transform" if they are implemented in the
    estimator used.

    The parameters of the estimator used to apply these methods are optimized
    by cross-validated search over parameter settings.

    In contrast to GridSearchCV, not all parameter values are tried out, but
    rather a fixed number of parameter settings is sampled from the specified
    distributions. The number of parameter settings that are tried is
    given by n_iter.

    If all parameters are presented as a list,
    sampling without replacement is performed. If at least one parameter
    is given as a distribution, sampling with replacement is used.
    It is highly recommended to use continuous distributions for continuous
    parameters.

    Parameters
    ----------
    estimator : estimator object.
        A object of that type is instantiated for each grid point.
        This is assumed to implement the scikit-learn estimator interface.
        Either estimator needs to provide a ``score`` function,
        or ``scoring`` must be passed.

    param_distributions : dict
        Dictionary with parameters names (string) as keys and distributions
        or lists of parameters to try. Distributions must provide a ``rvs``
        method for sampling (such as those from scipy.stats.distributions).
        If a list is given, it is sampled uniformly.

    n_iter : int, default=10
        Number of parameter settings that are sampled. n_iter trades
        off runtime vs quality of the solution.

    scoring : string, callable or None, default=None
        A string (see model evaluation documentation) or
        a scorer callable object / function with signature
        ``scorer(estimator, X, y)``.
        If ``None``, the ``score`` method of the estimator is used.

    fit_params : dict, optional
        Parameters to pass to the fit method.

    n_jobs : int, default=1
        Number of jobs to run in parallel.

    pre_dispatch : int, or string, optional
        Controls the number of jobs that get dispatched during parallel
        execution. Reducing this number can be useful to avoid an
        explosion of memory consumption when more jobs get dispatched
        than CPUs can process. This parameter can be:
            - None, in which case all the jobs are immediately
              created and spawned. Use this for lightweight and
              fast-running jobs, to avoid delays due to on-demand
              spawning of the jobs
            - An int, giving the exact number of total jobs that are
              spawned
            - A string, giving an expression as a function of n_jobs,
              as in '2*n_jobs'

    iid : boolean, default=True
        If True, the data is assumed to be identically distributed across
        the folds, and the loss minimized is the total loss per sample,
        and not the mean loss across the folds.

    cv : int, cross-validation generator or an iterable, optional
        Determines the cross-validation splitting strategy.
        Possible inputs for cv are:
        - None, to use the default 3-fold cross-validation,
        - integer, to specify the number of folds.
        - An object to be used as a cross-validation generator.
        - An iterable yielding train/test splits.
        For integer/None inputs, if the estimator is a classifier and ``y`` is
        either binary or multiclass, `StratifiedKFold` used. In all
        other cases, `KFold` is used.

    refit : boolean, default=True
        Refit the best estimator with the entire dataset.
        If "False", it is impossible to make predictions using
        this RandomizedSearchCV instance after fitting.

    verbose : integer
        Controls the verbosity: the higher, the more messages.

    random_state : int or RandomState
        Pseudo random number generator state used for random uniform sampling
        from lists of possible values instead of scipy.stats distributions.

    error_score : 'raise' (default) or numeric
        Value to assign to the score if an error occurs in estimator fitting.
        If set to 'raise', the error is raised. If a numeric value is given,
        FitFailedWarning is raised. This parameter does not affect the refit
        step, which will always raise the error.

    Attributes
    ----------
    grid_scores_ : list of named tuples
        Contains scores for all parameter combinations in param_grid.
        Each entry corresponds to one parameter setting.
        Each named tuple has the attributes:
            * ``parameters``, a dict of parameter settings
            * ``mean_validation_score``, the mean score over the
              cross-validation folds
            * ``cv_validation_scores``, the list of scores for each fold

    best_estimator_ : estimator
        Estimator that was chosen by the search, i.e. estimator
        which gave highest score (or smallest loss if specified)
        on the left out data. Not available if refit=False.

    best_score_ : float
        Score of best_estimator on the left out data.

    best_params_ : dict
        Parameter setting that gave the best results on the hold out data.

    Notes
    -----
    The parameters selected are those that maximize the score of the held-out
    data, according to the scoring parameter.
    If `n_jobs` was set to a value higher than one, the data is copied for each
    parameter setting(and not `n_jobs` times). This is done for efficiency
    reasons if individual jobs take very little time, but may raise errors if
    the dataset is large and not enough memory is available.  A workaround in
    this case is to set `pre_dispatch`. Then, the memory is copied only
    `pre_dispatch` many times. A reasonable value for `pre_dispatch` is `2 *
    n_jobs`.

    See Also
    --------
    `GridSearchCV`:
        Does exhaustive search over a grid of parameters.

    `ParameterSampler`:
        A generator over parameter settings, constructed from
        param_distributions.
    """

    def __init__(self, estimator, param_distributions, n_iter=10, scoring=None,
                 fit_params=None, n_jobs=1, iid=True, refit=True, cv=None,
                 verbose=0, pre_dispatch='2*n_jobs', random_state=None,
                 error_score='raise'):
        self.param_distributions = param_distributions
        self.n_iter = n_iter
        self.random_state = random_state

        super(_SK17RandomizedSearchCV, self).__init__(
            estimator=estimator, scoring=scoring, fit_params=fit_params,
            n_jobs=n_jobs, iid=iid, refit=refit, cv=cv, verbose=verbose,
            pre_dispatch=pre_dispatch, error_score=error_score)

    def fit(self, X, y=None):
        """Run fit on the estimator with randomly drawn parameters.

        Parameters
        ----------
        X : array-like, shape = [n_samples, n_features]
            Training vector, where n_samples in the number of samples and
            n_features is the number of features.
        y : array-like, shape = [n_samples] or [n_samples, n_output], optional
            Target relative to X for classification or regression;
            None for unsupervised learning.
        """
        sampled_params = ParameterSampler(self.param_distributions,
                                          self.n_iter,
                                          random_state=self.random_state)

        # the super class will handle the X, y validation
        return self._fit(X, y, sampled_params)
