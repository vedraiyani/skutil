from sklearn.base import BaseEstimator, TransformerMixin
import numpy as np
from sklearn.utils import check_array
from sklearn.utils.validation import check_is_fitted, FLOAT_DTYPES
from sklearn.externals.joblib import Parallel, delayed
from scipy import optimize


__all__ = ['YeoJohnsonTransformer']
ZERO = 1e-12


class YeoJohnsonTransformer(BaseEstimator, TransformerMixin):
    """Estimate a lambda parameter for each feature, and transform
       it to a distribution more-closely resembling a Gaussian bell
       using the Yeo-Johnson transformation.

    Parameters
    ----------
    n_jobs : int, 1 by default
       The number of jobs to use for the computation. This works by
       estimating each of the feature lambdas in parallel.

       If -1 all CPUs are used. If 1 is given, no parallel computing code
       is used at all, which is useful for debugging. For n_jobs below -1,
       (n_cpus + 1 + n_jobs) are used. Thus for n_jobs = -2, all CPUs but
       one are used.


    Attributes
    ----------
    lambda_ : ndarray, shape (n_features,)
       The lambda values corresponding to each feature
    """

    def __init__(self, n_jobs = 1):
        self.n_jobs = n_jobs

    def fit(self, X, y = None):
        """Estimate the lambdas, provided X

        Parameters
        ----------
        X : array-like, shape [n_samples, n_features]
            The data used for estimating the lambdas

        y : Passthrough for Pipeline compatibility
        """
        X = check_array(X, accept_sparse = False, copy = True,
                       ensure_2d = True, warn_on_dtype = True,
                       estimator = self, dtype = FLOAT_DTYPES)

        n_samples, n_features = X.shape
        if n_samples < 2:
            raise ValueError('n_samples should be at least two, but was %i' % n_samples)


        ## Now estimate the lambdas in parallel
        self.lambda_ = np.array(Parallel(n_jobs=self.n_jobs)(
            delayed(_yj_estimate_lambda_single_y)
            (y) for y in X.transpose()))

        return self

    def fit_transform(self, X, y = None):
        """Estimate the lambdas, provided X, and then
        return the transformed copy of X.

        Parameters
        ----------
        X : array-like, shape [n_samples, n_features]
            The data used for estimating the lambdas

        y : Passthrough for Pipeline compatibility
        """
        return self.fit(X, y).transform(X, y)

    def transform(self, X, y = None):
        """Perform Yeo-Johnson transformation

        Parameters
        ----------
        X : array-like, shape [n_samples, n_features]
            The data to transform
        """
        check_is_fitted(self, 'lambda_')

        X = check_array(X, accept_sparse = False, copy = True,
                       ensure_2d = True, warn_on_dtype = True,
                       estimator = self, dtype = FLOAT_DTYPES)

        _, n_features = X.shape
        lambdas_ = self.lambda_

        if not n_features == lambdas_.shape[0]:
            raise ValueError('dim mismatch in n_features')

        return np.array([_yj_transform_y(X[:,i], lambdas_[i])\
                         for i in xrange(n_features)]).transpose()

    def inverse_transform(self, X):
        """Transform back to the original representation

        Parameters
        ----------
        X : array-like, shape [n_samples, n_features]
            The data to inverse transform
        """
        check_is_fitted(self, 'lambda_')

        X = check_array(X, accept_sparse = False, copy = True,
                       ensure_2d = True, warn_on_dtype = True,
                       estimator = self, dtype = FLOAT_DTYPES)

        _, n_features = X.shape
        lambdas_ = self.lambda_

        if not n_features == lambdas_.shape[0]:
            raise ValueError('dim mismatch in n_features')

        return np.array([_yj_inv_transform_y(X[:,i], lambdas_[i])\
                         for i in xrange(n_features)]).transpose()

def _yj_inv_transform_y(y, lam):
    """Inverse transform a single y, given a single
    lambda value. No validation performed.

    Parameters
    ----------
    y : ndarray, shape (n_samples,)
       The vector being inverse transformed

    lam : ndarray, shape (n_lambdas,)
       The lambda value used for the inverse operation
    """
    z = []

    ## This is where it gets messy, but we can theorize that
    ## if the y is < 0 and the lambda meets the appropriate conditions,
    ## that the x was sub-zero to begin with.
    for x in y:
        if not lam == 0 and x >= 0:
            z.append(np.power(x * lam + 1, 1.0 / lam) - 1)
        elif lam == 0 and x >= 0:
            z.append(np.exp(x) - 1)
        elif not lam == 2 and x < 0:
            nmr = -(x * (2 - lam)) + 1
            z.append(-np.power(nmr, 1.0 / (2.0 - lam)) - 1)
        else:
            p_log = -x
            z.append(-(np.exp(p_log) - 1))

    return np.array(z)

def _yj_trans_single_x(x, lam):
    if x >= 0:
        ## Case 1: x >= 0 and lambda is not 0
        if not _eqls(lam, ZERO):
            return (np.power(x + 1, lam) - 1.0) / lam

        ## Case 2: x >= 0 and lambda is zero
        return np.log(x + 1)
    else :
        ## Case 2: x < 0 and lambda is not two
        if not _eqls(lam, 2.0):
            denom = 2.0 - lam
            numer = np.power((-x + 1), (2.0 - lam)) - 1.0
            return -numer / denom

        ## Case 4: x < 0 and lambda is two
        return -np.log(-x + 1)

def _yj_transform_y(y, lam):
    """Transform a single y, given a single lambda value.
    No validation performed.

    Parameters
    ----------
    y : ndarray, shape (n_samples,)
       The vector being transformed

    lam : ndarray, shape (n_lambdas,)
       The lambda value used for the transformation
    """
    return np.array([_yj_trans_single_x(x, lam) for x in y])

def _yj_estimate_lambda_single_y(y):
    """Estimate lambda for a single y, given a range of lambdas
    through which to search. No validation performed.

    Parameters
    ----------
    y : ndarray, shape (n_samples,)
       The vector being estimated against

    lambdas : ndarray, shape (n_lambdas,)
       The vector of lambdas to estimate with
    """

    ## Use customlog-likelihood estimator
    return _yj_normmax(y)

def _yj_normmax(x, brack = (-2, 2)):
    """Compute optimal YJ transform parameter for input data.

    Parameters
    ----------
    x : array_like
       Input array.
    brack : 2-tuple
       The starting interval for a downhill bracket search
    """

    ## Use MLE to compute the optimal YJ parameter
    def _mle(x, brack):
        def _eval_mle(lmb, data):
            ## Function to minimize
            return -_yj_llf(data, lmb)

        return optimize.brent(_eval_mle, brack = brack, args = (x,))

    return _mle(x, brack)

def _yj_llf(data, lmb):
    """Transform a y vector given a single lambda value,
    and compute the log-likelihood function. No validation
    is applied to the input.

    Parameters
    ----------
    data : array_like
       The vector to transform

    lmb : scalar
       The lambda value
    """

    data = np.asarray(data)
    N = data.shape[0]
    if 0 == N:
        raise ValueError('data is empty')
        #return np.nan

    y = _yj_transform_y(data, lmb)

    ## We can't take the log of data, as there could be
    ## zeros or negatives. Thus, we need to shift both distributions
    ## up by some artbitrary factor just for the LLF computation
    min_d, min_y = np.min(data), np.min(y)
    if min_d < ZERO:
        shift = np.abs(min_d) + 1
        data += shift

    ## Same goes for Y
    if min_y < ZERO:
        shift = np.abs(min_y) + 1
        y += shift

    ## Compute mean on potentially shifted data
    y_mean = np.mean(y, axis = 0)
    var = np.sum((y - y_mean)**2. / N, axis = 0)

    ## If var is 0.0, we'll get a warning. Means all the 
    ## values were nearly identical in y, so we will return
    ## NaN so we don't optimize for this value of lam
    if 0 == var:
        return np.nan

    llf = (lmb - 1) * np.sum(np.log(data), axis=0)
    llf -= N / 2.0 * np.log(var)

    return llf

def _eqls(lam, v):
    return np.abs(lam) <= v



## TESTING
from sklearn.datasets import load_iris
from numpy.random import poisson as ps
from numpy.random import normal as nm

sz = (150,4)
X = ps(size = sz) * nm(size = sz)
X = load_iris().data

trans = YeoJohnsonTransformer().fit(X)
transformed = trans.transform(X)

print "Transformed:"
print transformed

print "Inverse transformed:"
print trans.inverse_transform(transformed)
