import numpy as np
import pandas as pd

from scipy.integrate import odeint
from scipy.special import softmax, gammaln

import logging


class SamplingNInfectiousModel:

    def __init__(self,
                 nb_groups: int,
                 beta=None,
                 rel_lockdown_beta=None,
                 rel_postlockdown_beta=None,
                 rel_beta_as=None,
                 prop_as=None,
                 prop_m=None,
                 prop_s_to_h=None,
                 prop_h_to_c=None,
                 prop_h_to_d=None,
                 prop_c_to_d=None,
                 time_incubate=None,
                 time_infectious=None,
                 time_s_to_h=None,
                 time_s_to_c=None,
                 time_h_to_c=None,
                 time_h_to_r=None,
                 time_h_to_d=None,
                 time_c_to_r=None,
                 time_c_to_d=None,
                 y0=None,
                 imported_func=None):
        logging.info('Initizializing model')

        # infectious and relative to infectious rates
        beta = np.asarray(beta)
        rel_lockdown_beta = np.asarray(rel_lockdown_beta)
        rel_postlockdown_beta = np.asarray(rel_postlockdown_beta)
        rel_beta_as = np.asarray(rel_beta_as)

        # proportions
        prop_as = np.asarray(prop_as)
        prop_m = np.asarray(prop_m)
        prop_s_to_h = np.asarray(prop_s_to_h)
        prop_h_to_c = np.asarray(prop_h_to_c)
        prop_h_to_d = np.asarray(prop_h_to_d)
        prop_c_to_d = np.asarray(prop_c_to_d)

        # times
        time_incubate = np.asarray(time_incubate)
        time_infectious = np.asarray(time_infectious)
        time_s_to_h = np.asarray(time_s_to_h)
        time_s_to_c = np.asarray(time_s_to_c)
        time_h_to_c = np.asarray(time_h_to_c)
        time_h_to_r = np.asarray(time_h_to_r)
        time_h_to_d = np.asarray(time_h_to_d)
        time_c_to_r = np.asarray(time_c_to_r)
        time_c_to_d = np.asarray(time_c_to_d)

        # calculated vars
        prop_s = 1 - prop_as - prop_m
        prop_s_to_c = 1 - prop_s_to_h
        prop_h_to_r = 1 - prop_h_to_c - prop_h_to_d

        # collect variables into specific dictionaries

        beta_vars = {
            'beta': beta,
            'rel_lockdown_beta': rel_lockdown_beta,
            'rel_postlockdown_beta': rel_postlockdown_beta,
            'rel_beta_as': rel_beta_as
        }

        prop_vars = {
            'prop_as': prop_as,
            'prop_m': prop_m,
            'prop_s': prop_s,
            'prop_s_to_h': prop_s_to_h,
            'prop_s_to_c': prop_s_to_c,
            'prop_h_to_c': prop_h_to_c,
            'prop_h_to_d': prop_h_to_d,
            'prop_h_to_r': prop_h_to_r,
            'prop_c_to_d': prop_c_to_d
        }

        time_vars = {
            'time_incubate': time_incubate,
            'time_infectious': time_infectious,
            'time_s_to_h': time_s_to_h,
            'time_s_to_c': time_s_to_c,
            'time_h_to_c': time_h_to_c,
            'time_h_to_r': time_h_to_r,
            'time_h_to_d': time_h_to_d,
            'time_c_to_r': time_c_to_r,
            'time_c_to_d': time_c_to_d,
        }

        # assert specific properties of variables
        for key, value in beta_vars.items():
            assert np.all(beta >= 0), f"Value in '{key}' is smaller than 0"
        for key, value in prop_vars.items():
            assert np.all(value <= 1), f"Value in proportion '{key}' is greater than 1"
            assert np.all(value >= 1), f"Value in proportion '{key}' is smaller than 0"
        for key, value in time_vars.items():
            assert np.all(value >= 0), f"Value in time '{key}' is smaller than 0."


        # intrinsic parameter measuring the number of internal states of which to keep track
        nb_states = 16

        # detect the number of samples made, check for consistency, and assert the shapes of the parameters
        nb_samples, (scalar_vars, group_vars, sample_vars) = _determine_sample_vars({
            **beta_vars,
            **prop_vars,
            **time_vars
        }, nb_groups)

        logging.info(f'Scalar variables: {list(scalar_vars.keys())}')
        logging.info(f'Group variables: {list(group_vars.keys())}')
        logging.info(f'Sampled variables: {list(sample_vars.keys())}')

        # check if y0 shape is correct
        y0 = np.asarray(y0)
        assert y0.size == nb_states * nb_groups * nb_samples, \
            f"y0 should have size {nb_states * nb_groups * nb_samples}, got {y0.size} instead"

        # find the total population from y0, assumed to be constant or change very little over time
        n = np.sum(y0.reshape(nb_samples, nb_groups * nb_states), axis=1, keepdims=True)

        # build infectious function from given parameters
        def infectious_func(t):
            if t < -11:
                return 1
            elif -11 <= t < 0:
                return 1 - (1 - rel_lockdown_beta) / 11 * (t - 11)
            elif 0 <= t < 5 * 7:
                return rel_lockdown_beta
            # else
            return rel_postlockdown_beta

        # check imported func
        if imported_func is not None:
            assert callable(imported_func), "imported_func is not callable"
        else:
            imported_func = lambda t: 0

        # set properties
        self.nb_groups = nb_groups
        self.nb_states = nb_states
        self.nb_samples = nb_samples
        self.nb_infectious = 10  # for consistency with previous versions of the ASSA model

        # beta proporties
        self.beta = beta
        self.rel_beta_as = rel_beta_as
        self.rel_lockdown_beta = rel_lockdown_beta
        self.rel_postlockdown_beta = rel_postlockdown_beta

        # proportion proporties
        self.prop_as = prop_as
        self.prop_m = prop_m
        self.prop_s = prop_s
        self.prop_s_to_h = prop_s_to_h
        self.prop_h_to_c = prop_h_to_c
        self.prop_h_to_d = prop_h_to_d
        self.prop_h_to_r = prop_h_to_r
        self.prop_c_to_d = prop_c_to_d

        # time properties
        self.time_inc = time_incubate
        self.time_infectious = time_infectious
        self.time_s_to_h = time_s_to_h
        self.time_s_to_c = time_s_to_c
        self.time_h_to_c = time_h_to_c
        self.time_h_to_r = time_h_to_r
        self.time_h_to_d = time_h_to_d
        self.time_c_to_r = time_c_to_r
        self.time_c_to_d = time_c_to_d

        # y0 properties
        self.y0 = y0
        self.n = n

        # scalar properties
        self.scalar_vars = scalar_vars
        self.group_vars = group_vars
        self.sample_vars = sample_vars

        # function properties
        self.infectious_func = infectious_func
        self.imported_func = imported_func

        # private proporties relating to whether the model has been internally solved at least once
        self._solved = False
        self._t = None
        self.solution = None

        # initialising proporties for use in the calculate_sir_posterior function
        self.resample_vars = None
        self.log_weights = None
        self.weights = None

    def _ode(self, y, t):
        # get seird
        s, e, i_as, i_m, i_s, i_i_h, i_i_icu, i_h, i_icu, _, _, _, _, _ = self._get_seird_from_flat_y(y)

        # get meta vars
        inf_s_prop = 1 - self.prop_as - self.prop_m
        time_i_to_h = self.time_s_to_h - self.time_infectious
        time_i_to_icu = self.time_s_to_c - self.time_infectious


        # solve seird equations
        ds = - 1 / self.n * self.infectious_func(t) * self.beta * np.sum(self.rel_beta_as * i_as + i_m + i_s, axis=1, keepdims=True) * s
        de = 1 / self.n * self.infectious_func(t) * self.beta * np.sum(self.rel_beta_as * i_as + i_m + i_s, axis=1, keepdims=True) * s - e / self.time_inc
        di_as = self.prop_as * e / self.time_inc - i_as / self.time_infectious
        di_m = self.prop_m * e / self.time_inc - i_m / self.time_infectious
        di_s = inf_s_prop * e / self.time_inc - i_s / self.time_infectious
        di_i_h = self.prop_s_to_h * i_s / self.time_infectious - i_i_h / time_i_to_h
        di_i_icu = (1 - self.prop_s_to_h) * i_s / self.time_infectious - i_i_icu / time_i_to_icu
        di_h = i_i_h / time_i_to_h - self.f_hosp_icu_prop * i_h / self.time_h_to_c - (1 - self.f_hosp_icu_prop) * i_h / self.time_h_to_r
        di_icu = self.f_hosp_icu_prop * i_h / self.time_h_to_c + i_i_icu / time_i_to_icu - self.f_icu_d_prop * i_icu / self.time_c_to_d - (1 - self.f_icu_d_prop) * i_icu / self.time_c_to_r
        dr_as = i_as / self.time_infectious
        dr_m = i_m / self.time_infectious
        # dr_s = np.zeros((self.nb_samples, self.nb_groups))
        # dr_i = np.zeros((self.nb_samples, self.nb_groups))
        dr_h = (1 - self.f_hosp_icu_prop) * i_h / self.time_h_to_r
        dr_icu = (1 - self.f_icu_d_prop) * i_icu / self.time_c_to_r
        dd_icu = self.f_icu_d_prop * i_icu / self.time_c_to_d

        dydt = np.concatenate([
            ds.reshape(self.nb_samples, self.nb_groups, 1),
            de.reshape(self.nb_samples, self.nb_groups, 1),
            di_as.reshape(self.nb_samples, self.nb_groups, 1),
            di_m.reshape(self.nb_samples, self.nb_groups, 1),
            di_s.reshape(self.nb_samples, self.nb_groups, 1),
            di_i_h.reshape(self.nb_samples, self.nb_groups, 1),
            di_i_icu.reshape(self.nb_samples, self.nb_groups, 1),
            di_h.reshape(self.nb_samples, self.nb_groups, 1),
            di_icu.reshape(self.nb_samples, self.nb_groups, 1),
            dr_as.reshape(self.nb_samples, self.nb_groups, 1),
            dr_m.reshape(self.nb_samples, self.nb_groups, 1),
            dr_h.reshape(self.nb_samples, self.nb_groups, 1),
            dr_icu.reshape(self.nb_samples, self.nb_groups, 1),
            dd_icu.reshape(self.nb_samples, self.nb_groups, 1)
        ], axis=-1).reshape(-1)

        return dydt

    def solve(self, t, y0=None):
        y0 = self.y0 if y0 is None else y0
        if not self._solved:
            sol = odeint(self._ode, y0, t).reshape(-1, self.nb_samples, self.nb_groups, self.nb_states).clip(min=0)
            self.solution = sol
            self._t = t
            self._solved = True
            return sol
        else:
            if np.all(t != self._t) or np.all(y0 != self.y0):
                sol = odeint(self._ode, y0, t).reshape(-1, self.nb_samples, self.nb_groups, self.nb_states).clip(min=0)
                self._t = t
                self.solution = sol
                return sol
            else:
                return self.solution

    def calculate_sir_posterior(self,
                                t,
                                i_d_obs=None,
                                i_h_obs=None,
                                i_icu_obs=None,
                                d_icu_obs=None,
                                ratio_as_detected=0.,
                                ratio_m_detected=0.3,
                                ratio_s_detected=1.0,
                                ratio_resample: float = 0.1,
                                y0=None,
                                smoothing=1) -> dict:
        # cast variables
        t = np.asarray(t)
        i_d_obs = None if i_d_obs is None else np.asarray(i_d_obs).reshape(-1, 1, 1).astype(int)
        i_h_obs = None if i_h_obs is None else np.asarray(i_h_obs).reshape(-1, 1, 1).astype(int)
        i_icu_obs = None if i_icu_obs is None else np.asarray(i_icu_obs).reshape(-1, 1, 1).astype(int)
        d_icu_obs = None if d_icu_obs is None else np.asarray(d_icu_obs).reshape(-1, 1, 1).astype(int)

        # assert shapes
        # TODO: Implement linear interpolation for cases where t does not directly match the data
        # TODO: Implement checks for when data is group specific

        # assert i_d_obs.ndim == 1 and i_d_obs.size == t.size, "Observed detected cases does not match time size"
        # assert i_h_obs.ndim == 1 and i_h_obs.size == t.size, "Observed hospital cases does not match time size"
        # assert i_icu_obs.ndim == 1 and i_icu_obs.size == t.size, "Observed ICU cases does not match time size"
        # assert d_icu_obs.ndim == 1 and d_icu_obs.size == t.size, "Observed deaths does not match time size"

        logging.info('Solving system')
        y = self.solve(t, y0)

        logging.info('Collecting necessary variables from solution')
        i_as = y[:, :, :, 2]
        i_m = y[:, :, :, 3]
        i_s = y[:, :, :, 4]
        i_i_h = y[:, :, :, 5]
        i_i_icu = y[:, :, :, 6]
        i_h = y[:, :, :, 7]
        i_icu = y[:, :, :, 8]
        r_as = y[:, :, :, 9]
        r_m = y[:, :, :, 10]
        r_h = y[:, :, :, 11]
        r_icu = y[:, :, :, 12]
        d_icu = y[:, :, :, 13]

        cum_detected_samples = ratio_as_detected * (i_as + r_as) + ratio_m_detected * (i_m + r_m) \
                               + ratio_s_detected * (i_s + i_i_h + i_i_icu + i_h + i_icu + r_h + r_icu + d_icu)


        # model detected cases as poisson distribution y~P(lambda=detected_cases) with stirling's approximation for log y!
        logging.info('Calculating log weights')
        log_weights_detected = 0 if i_d_obs is None else _log_poisson(i_d_obs, cum_detected_samples)
        log_weights_hospital = 0 if i_h_obs is None else _log_poisson(i_h_obs, i_h)
        log_weights_icu = 0 if i_icu_obs is None else _log_poisson(i_icu_obs, i_icu)
        log_weights_dead = 0 if d_icu_obs is None else _log_poisson(d_icu_obs, d_icu)

        log_weights = log_weights_detected + log_weights_hospital + log_weights_icu + log_weights_dead
        weights = softmax(log_weights/smoothing)

        logging.info(f'log_weights_min: {log_weights.min()}')
        logging.info(f'log_weights_max: {log_weights.max()}')
        logging.info(f'Proportion weights above 0: {np.mean(weights > 0):.6}')
        logging.info(f'Proportion weights above 1E-20: {np.mean(weights > 1E-20):.6}')
        logging.info(f'Proportion weights above 1E-10: {np.mean(weights > 1E-10):.8}')
        logging.info(f'Proportion weights above 1E-3: {np.mean(weights > 1E-3):.10}')
        logging.info(f'Proportion weights above 1E-2: {np.mean(weights > 1E-2):.10}')
        logging.info(f'Proportion weights above 1E-1: {np.mean(weights > 1E-1):.10}')
        logging.info(f'Proportion weights above 0.5: {np.mean(weights > 0.5):.10}')

        # resample the sampled variables
        m = int(np.round(self.nb_samples * ratio_resample))
        logging.info(f'Resampling {list(self.sample_vars.keys())} {m} times from {self.nb_samples} original samples')
        resample_indices = np.random.choice(self.nb_samples, m, p=weights)
        resample_vars = {}
        for key, value in self.sample_vars.items():
            logging.info(f'Resampling {key}')
            resample_vars[key] = value[resample_indices]
        logging.info(f'Succesfully resampled {list(resample_vars.keys())} {m} times from {self.nb_samples} original samples')

        self.resample_vars = resample_vars
        self.log_weights = log_weights
        self.weights = weights

    def _get_seird_from_flat_y(self, y):
        y = y.reshape(self.nb_samples, self.nb_groups, self.nb_states)
        s = y[:, :, 0]
        e = y[:, :, 1]
        i_as = y[:, :, 2]
        i_m = y[:, :, 3]
        i_s = y[:, :, 4]
        i_i_h = y[:, :, 5]
        i_i_icu = y[:, :, 6]
        i_h = y[:, :, 7]
        i_icu = y[:, :, 8]
        r_as = y[:, :, 9]
        r_m = y[:, :, 10]
        r_h = y[:, :, 11]
        r_icu = y[:, :, 12]
        d_icu = y[:, :, 13]

        return s, e, i_as, i_m, i_s, i_i_h, i_i_icu, i_h, i_icu, r_as, r_m, r_h, r_icu, d_icu


def _determine_sample_vars(vars: dict, nb_groups):
    dim_dict = {}
    for key, value in vars.items():
        dim_dict[key] = value.ndim

    # determine scalars, group specific vars, and variables with samples
    scalar_vars = {}
    group_vars = {}
    sample_vars = {}
    nb_samples = None
    for key, value in vars.items():
        if value.ndim == 0:
            # scalar
            scalar_vars[key] = value
        elif value.ndim == 1:
            # shouldn't exist, this is either an ill-defined sampler or ill-defined group var
            raise ValueError(f'Variable {key} should either be zero or two dimensional. This is either an\n'
                             'ill-defined sampler or population group specific variable. If the former, it\n'
                             'take the shape [nb_samples x 1] or [nb_samples x nb_groups], if the latter, it\n'
                             'should take the value [1 x nb_groups].')
        elif value.ndim == 2:
            # sample variable
            val_shape = value.shape
            if val_shape[0] > 1:
                nb_samples = val_shape[0]
            elif val_shape == (1, nb_groups):
                group_vars[key] = value
            else:
                raise ValueError(f'Variable {key} seems to be an ill-defined group specific variable. It should take\n'
                                 f'a shape of (1, {nb_groups}), got {val_shape} instead.')
            if nb_samples:
                if val_shape[0] != nb_samples:
                    raise ValueError(f'Inconsistencies in number of samples made for variable {key}.\n'
                                     f'A previous variable had {nb_samples} samples, this variables\n'
                                     f'as {val_shape[0]} samples.')
                elif val_shape != (nb_samples, 1) and val_shape != (nb_samples, nb_groups):
                    raise ValueError(f'Variable {key} is either an\n'
                                     f'ill-defined sampler or population group specific variable. If the former, it\n'
                                     f'take the shape ({nb_samples}, 1) or ({nb_samples}, {nb_groups}), if the latter,\n'
                                     f'it should take the value (1, {nb_groups}). Got {val_shape} instead.')
                else:
                    sample_vars[key] = value
        else:
            raise ValueError(f'Variable {key} has too many dimension. Should be 0 or 2, got {value.ndims}')

    if not nb_samples:
        nb_samples = 1

    return nb_samples, (scalar_vars, group_vars, sample_vars)


def _log_k_factorial(k):
    if k == 0:
        return 0
    else:
        return 1 / 2 * np.log(2 * np.pi * k) + k * (np.log(k) - 1)


def _log_l(l):
    if l <= 1:
        return 0
    else:
        return np.log(l)


_log_k_factorial = np.vectorize(_log_k_factorial)
_log_l = np.vectorize(_log_l)


def _log_poisson(k, l):
    out = k * np.log(l+1E-20) - l - gammaln(k+1)
    out = np.sum(out, axis=(0, 2))
    return out