import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import PCA, TruncatedSVD
from sklearn.utils.validation import check_is_fitted
from ..utils import *
from ..base import *



__all__ = [
    'SelectivePCA',
    'SelectiveTruncatedSVD'
]


###############################################################################
class BaseSelectiveDecomposer:
    """Any decomposing class should implement
    this mixin. It will return the SVD or PCA decomposition.
    """

    def get_decomposition(self):
        if hasattr(self, 'pca_'):
            return self.pca_
        elif hasattr(self, 'svd_'):
            return self.svd_
        else:
            raise ValueError('class does not have pca_ or svd_ attribute')



###############################################################################
class SelectivePCA(BaseEstimator, TransformerMixin, SelectiveMixin, BaseSelectiveDecomposer):
    """A class that will apply PCA only to a select group
    of columns. Useful for data that contains categorical features
    that have not yet been dummied, or for dummied features we don't want
    decomposed.

    Parameters
    ----------
    cols : array_like (string)
        names of columns on which to apply scaling

    n_components : int, float, None or string
        Number of components to keep.
        if n_components is not set all components are kept:

            n_components == min(n_samples, n_features)

        if n_components == 'mle' and svd_solver == 'full', Minka\'s MLE is used
        to guess the dimension
        if ``0 < n_components < 1`` and svd_solver == 'full', select the number
        of components such that the amount of variance that needs to be
        explained is greater than the percentage specified by n_components
        n_components cannot be equal to n_features for svd_solver == 'arpack'.

    as_df : boolean, default True
        Whether to return a pandas DataFrame

    whiten : bool, optional (default False)
        When True (False by default) the `components_` vectors are multiplied
        by the square root of n_samples and then divided by the singular values
        to ensure uncorrelated outputs with unit component-wise variances.
        Whitening will remove some information from the transformed signal
        (the relative variance scales of the components) but can sometime
        improve the predictive accuracy of the downstream estimators by
        making their data respect some hard-wired assumptions.


    Attributes
    ----------
    cols_ : array_like (string)
        the columns

    pca_ : the PCA object
    """

    def __init__(self, cols=None, n_components=None, whiten=False, as_df=True):
        self.cols_ = cols
        self.n_components = n_components
        self.whiten = whiten
        self.as_df = as_df

    def fit(self, X, y = None):
        validate_is_pd(X)

        ## If cols is None, then apply to all by default
        if not self.cols_:
            self.cols_ = X.columns

        ## fails thru if names don't exist:
        self.pca_ = PCA(
            n_components=self.n_components,
            whiten=self.whiten).fit(X[self.cols_])

        return self

    def transform(self, X, y = None):
        check_is_fitted(self, 'pca_')
        validate_is_pd(X)

        X = X.copy()
        other_nms = [nm for nm in X.columns if not nm in self.cols_]

        transform = self.pca_.transform(X[self.cols_])
        left = pd.DataFrame.from_records(data=transform, columns=[('PC%i'%(i+1)) for i in range(transform.shape[1])])

        x = pd.concat([left, X[other_nms]], axis=1)

        return x if self.as_df else x.as_matrix()


###############################################################################
class SelectiveTruncatedSVD(BaseEstimator, TransformerMixin, SelectiveMixin, BaseSelectiveDecomposer):
    """A class that will apply truncated SVD (LSA) only to a select group
    of columns. Useful for data that contains categorical features
    that have not yet been dummied, or for dummied features we don't want
    decomposed. TruncatedSVD is the equivalent of Latent Semantic Analysis,
    and returns the "concept space" of the decomposed features.

    Parameters
    ----------
    cols : array_like (string)
        names of columns on which to apply scaling

    n_components : int, default = 2
        Desired dimensionality of output data.
        Must be strictly less than the number of features.
        The default value is useful for visualisation. For LSA, a value of
        100 is recommended.

    algorithm : string, default = "randomized"
        SVD solver to use. Either "arpack" for the ARPACK wrapper in SciPy
        (scipy.sparse.linalg.svds), or "randomized" for the randomized
        algorithm due to Halko (2009).

    n_iter : int, optional (default 5)
        Number of iterations for randomized SVD solver. Not used by ARPACK.
        The default is larger than the default in `randomized_svd` to handle
        sparse matrices that may have large slowly decaying spectrum.

    as_df : boolean, default True
        Whether to return a pandas DataFrame


    Attributes
    ----------
    cols_ : array_like (string)
        the columns

    svd_ : the SVD object
    """

    def __init__(self, cols=None, n_components=2, algorithm='randomized', n_iter=5, as_df=True):
        self.cols_ = cols
        self.n_components = n_components
        self.algorithm = algorithm
        self.n_iter = n_iter
        self.as_df = as_df

    def fit(self, X, y = None):
        validate_is_pd(X)

        ## If cols is None, then apply to all by default
        if not self.cols_:
            self.cols_ = X.columns

        ## fails thru if names don't exist:
        self.svd_ = TruncatedSVD(
            n_components=self.n_components,
            algorithm=self.algorithm,
            n_iter=self.n_iter).fit(X[self.cols_])

        return self

    def transform(self, X, y = None):
        check_is_fitted(self, 'svd_')
        validate_is_pd(X)

        X = X.copy()
        other_nms = [nm for nm in X.columns if not nm in self.cols_]

        transform = self.svd_.transform(X[self.cols_])
        left = pd.DataFrame.from_records(data=transform, columns=[('Concept%i'%(i+1)) for i in range(transform.shape[1])])

        x = pd.concat([left, X[other_nms]], axis=1)

        return x if self.as_df else x.as_matrix()


