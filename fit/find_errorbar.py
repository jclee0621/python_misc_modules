from pylab import *
import numpy as np
import PicoQuantUtils_FastFit as pq
import glob
import sys
import cPickle
from scipy.signal import cspline1d, cspline1d_eval
from scipy.optimize import fmin

infile=None

def load_wire( fname ):
    if infile is None: raise ValueError("Must set find_errorbar.infile !!!")
    d = cPickle.load( open( infile+".pkl", "rb" ) )
    for t in d:
        if t['fname'] == fname:
            return t['fitresults'] #, sum(abs(t['acorr']))

def do_fit( bestfittrace, l, a, fixed, dispersion, force_guess ):
    print bestfittrace.fname, fixed
    trace = pq.Trace( bestfittrace.fname )
    if bestfittrace.in_counts_per_second: trace.counts_per_second()
    trace.wrapcurves( time=bestfittrace.wraptime )
    trace.set_irf(bestfittrace.irf.fname, wraptime=bestfittrace.irf.wraptime, dispersion=bestfittrace.irf_dispersion)
    #trace.set_irf('/home/kc/lab/DATA/2011/2011_08_11_SiO2Alq3Cavities/IRF_760nm_3e4cps_30sec_APCfiber_14Aug2011.phd',
    #    wraptime=10.0, dispersion=dispersion )

    if len(l) == 1:
        guess = dict( l0=l, a0=a, b=0.0, tshift=-0.5)
    elif len(l) == 2:
        l0, l1 = l
        a0, a1 = a
        guess = dict( l0=l0, l1=l1, a0=a0, a1=a1, b=1.0, tshift=-0.5)
    elif len(l) == 3:
        l0, l1, l2 = l
        a0, a1, a2 = a
        guess = dict( l0=l0, l1=l1, l2=l2,
                      a0=a0, a1=a1, a2=a2,
                      b=1.0, tshift=-0.5)
    else:
        l0, l1, l2, l3 = l
        a0, a1, a2, a3 = a
        guess = dict( l0=l0, l1=l1, l2=l2, l3=l3,
                      a0=a0, a1=a1, a2=a2, a3=a3,
                      b=1.0, tshift=-0.5)
                      
    for k, v in force_guess.iteritems():
        if k not in fixed: guess[k] = v
    
    trace.fit_exponential( tstart=trace.get_max()[0]+0.01,
        guess=guess, deconvolve=True, verbose=True, fixed_params=fixed )
    
    return trace.fitresults



def get_errorbar( fv, fname=None, trace=None, frac=0.1, additional_fixed=None, plotresult=False, guess=dict() ):
    """ Use Lakowicz's f-statistic method to find the 95% confidence interval on a fitting parameter.
        fv -- a string/dictionary key identifying the parameter to find a confidence interval on.
        fname -- (optional, can use trace instead) fname of data file to fit.
        trace -- can use trace instead of fname to pass in info on wraptime and irf fname, etc.
        frac -- the fractional change in the parameter to use for the intial 5-point mesh
        additional_fixed -- any parameters you want to hold fixed during the fitting
        plotresult -- plot the f-statistic curve?
        guess -- dictionary of initial parameters for the fit (by default, best-fit values are used)
    """
    #bestfit, bestacorr = load_wire( fname )
    if fname is not None:
        raise ValueError('have modified this to prefer working with actual traces to forward wraptime, etc., to do_fit')
        bestfit = load_wire( fname )
    if trace is not None:
        assert fname==None
        bestfit = trace.fitresults.copy()
    bestChi2 = bestfit['ReducedChi2']
    irf = bestfit['irf_dispersion']
    lkeys = ['l0']
    akeys = ['a0']
    if bestfit.has_key('l1'):
        lkeys.append('l1')
        akeys.append('a1')
    if bestfit.has_key('l2'):
        lkeys.append('l2')
        akeys.append('a2')
    if bestfit.has_key('l3'):
        lkeys.append('l3')
        akeys.append('a3')
    fixedparams = [fv]
    if additional_fixed is not None: fixedparams += additional_fixed
    fv_best = bestfit[fv]

    # If holding l1-l3 lifetimes fixed, as we did
    # for the actual fit, then Fx should equal 1.0 at the 'bestfit' value of the parameter.
    # But if l1-l3 are allowed to vary (making a more conservative error bar), then
    # Fx may be lower than 1.0, and the minimum may not be at the "bestfit" value.
    # This is to say that the bestfit of the constrained fit may not be the bestfit of the unconstrained fit.

    #Fx = 1.0038 # Threshold found from F-statistic 1600 deg. freedom (~half trace points, following Fundamentals Of Fluorescence Spectroscopy)
    Fx = 1.001858 # Threshold found from F-statistic on all 3282 points. Seems easier to justify
    Fx_list = [] # later we'll sort these in order of increasing parameter value to enable interpolation
    val_step = frac*fv_best/2
    argvals = arange( fv_best*(1.0-frac), fv_best*(1.0+frac)+val_step, val_step )

    # do a coarse (5-pt) run across the data
    for val in argvals:
        bestfit[ fv ] = val
        l = [ bestfit[key] for key in lkeys ]
        a = [ bestfit[key] for key in akeys ]
        params = do_fit( trace, l, a, fixedparams, irf, guess )
        Fx_list.append( [val, params['ReducedChi2']/bestChi2] )

    if all(array(Fx_list)[:,1]>Fx):
        Fx_list = []
        for val in argvals:
            bestfit[ fv ] = val
            cpy = bestfit.copy()
            for key in lkeys:
                if key not in fixedparams: cpy[key] = 1.25*bestfit[key]
            for key in akeys:
                if key not in fixedparams: cpy[key] = 1.5*bestfit[key]
            l = [ cpy[key] for key in lkeys ]
            a = [ cpy[key] for key in akeys ]
            params = do_fit( trace, l, a, fixedparams, irf, guess )
            Fx_list.append( [val, params['ReducedChi2']/bestChi2] )

    if all(array(Fx_list)[:,1]>Fx): raise ValueError("Problem fitting: always above Fx. Min: %f" % (array(Fx_list)[:,1].min()))
    

    # if the left side (low param value) didn't exceed Fx threshold, extend
    val = argvals[0]
    while Fx_list[0][1] < Fx:
        val -= val_step
        if val < 0: 
            if fv in ['l1', 'l2', 'l3']:
                raise ValueError("long-time component just went negative...")
            else:
                break
        bestfit[ fv ] = val
        l = [ bestfit[key] for key in lkeys ]
        a = [ bestfit[key] for key in akeys ]
        params = do_fit( trace, l, a, fixedparams, irf, guess )
        Fx_list.append( [val, params['ReducedChi2']/bestChi2] )
        Fx_list.sort( key=lambda x: x[0] ) # sort by first element (parameter value)

    # if the right side (high param value) didn't exceed Fx threshold, extend
    val = argvals[-1]
    while Fx_list[-1][1] < Fx:
        val += val_step
        bestfit[ fv ] = val
        l = [ bestfit[key] for key in lkeys ]
        a = [ bestfit[key] for key in akeys ]
        params = do_fit( trace, l, a, fixedparams, irf, guess )
        Fx_list.append( [val, params['ReducedChi2']/bestChi2] )
        Fx_list.sort( key=lambda x: x[0] ) # sort by first element (parameter value)


    # interpolate to find values at threshold
    Fx_array = array( Fx_list )
    splines = cspline1d( Fx_array[:,1] )
    interp_val = linspace( Fx_array[0,0], Fx_array[-1,0], 500 )
    interp_Fx = cspline1d_eval( splines, interp_val, dx=val_step, x0=Fx_array[:,0].min() )
    error_bar = [ interp_val[find(interp_Fx<Fx)[0]], interp_val[find(interp_Fx<Fx)[-1]] ]

    if plotresult:
        fig = figure(1)
        #fig.clf()
        ax_chi = fig.add_subplot(111)
        ax_chi.cla()
        ax_chi.plot( interp_val, interp_Fx, '-k' )
        ax_chi.plot( interp_val, [Fx]*len(interp_val), '--k' )
        ax_chi.plot( Fx_array[:,0], Fx_array[:,1], 'sg' )
        ax_chi.plot( error_bar, [Fx]*2, '-b', lw=3.0 )

        ax_chi.set_ylim([0.99, 1.01])
        fig.show()
        fig.canvas.draw()

    return error_bar

def long_time_errorbars( fnames, fv, frac=0.1, additional_fixed=None, plotresult=False ):
    # finding error bar in the "fixed" parameters... I think this is similar to what
    # I did above but with average RChi2 across all traces
    # I tried to recalculate a lower Fx value because DOF increased from 3282 to 3282*len(fnames),
    # but the calc. only could handle <10000 DOF, and Fx only changed from 1.001858 to 1.001845.

    lkeys = ['l0','l1','l2','l3']
    akeys = ['a0','a1','a2','a3']
    fixedparams = [fv]
    if additional_fixed is not None: fixedparams += additional_fixed
    #Fx = 1.001845 # Threshold found from F-statistic on 9999 points. (max of calculator, faking 3282*21).
    Fx = 1.001858 # Threshold found from F-statistic on 3282 pts.
    Fx_list = [] # later we'll sort these in order of increasing parameter value to enable interpolation

    # first get best_avg_RChi2:
    bestfits = []
    chi2 = []
    for fname in fnames:
        bestfit, bestacorr = load_wire( fname )
        bestfits.append( bestfit )
        chi2.append( bestfit['ReducedChi2'] )
    best_avg_RChi2 = np.mean(chi2)
    
    # setup initial coarse scan
    assert bestfit.has_key("l3")
    fv_best = bestfit[fv]
    val_step = frac*fv_best/2.0
    argvals = arange( fv_best*(1.0-frac), fv_best*(1.0+frac)+val_step, val_step )

    def fmin_kernel( twoT, *args ):
        avg_RChi2 = 0.0
        fv_value = args[0]
        longT_floating = [ key for key in ['l1','l2','l3'] if key != fv ] # the two longTime components we're optimizing
        chi2 = []
        for i,fname in enumerate(fnames):
            bestfit = bestfits[i].copy()
            bestfit[ fv ] = fv_value
            bestfit[ longT_floating[0] ] = twoT[0]
            bestfit[ longT_floating[1] ] = twoT[1]
            l = [ bestfit[key] for key in lkeys ]
            a = [ bestfit[key] for key in akeys ]
            irf = bestfit['irf_dispersion']
             # all three long-components are fixed for this fit, but the
             # values they are fixed at are set at different levels:
             # fv is the component we're finding an errorbar for, and
             # it is set by the function long_time_errorbars.
             # The other two are allowed to "float" in response, but
             # not float freely for each trace individually; we're
             # looking for an error bar for the global fit across all
             # cavities on a given sample, so we constrain them for each
             # individual fit but let fmin play with them to minimize
             # the mean reduced Chi squared across all data sets.
            params = do_fit( fname, l, a, ['l1','l2','l3'], irf )
            chi2.append( params['ReducedChi2'] )
        return np.mean(chi2)

    # do a coarse (5-pt) run across the data
    twoT_guess = [ bestfit[key] for key in ['l1','l2','l3'] if key != fv ] # the two longTime components we're optimizing
    for val in argvals:
        res = fmin( fmin_kernel, twoT_guess, args=(val,), xtol=0.005, ftol=0.005, full_output=1 )
        avg_RChi2 = res[1]
        Fx_list.append( [val, avg_RChi2/best_avg_RChi2] )

    assert not all(array(Fx_list)[:,1]>Fx)

    # if the left side (low param value) didn't exceed Fx threshold, extend
    val = argvals[0]
    while Fx_list[0][1] < Fx:
        val -= val_step
        if val < 0: 
            if fv in ['l1', 'l2', 'l3']:
                raise ValueError("long-time component just went negative...")
            else:
                break
        res = fmin( fmin_kernel, twoT_guess, args=(val,), xtol=0.005, ftol=0.005, full_output=1 )
        avg_RChi2 = res[1]
        Fx_list.append( [val, avg_RChi2/best_avg_RChi2] )
        Fx_list.sort( key=lambda x: x[0] ) # sort by first element (parameter value)

    # if the right side (high param value) didn't exceed Fx threshold, extend
    val = argvals[-1]
    while Fx_list[-1][1] < Fx:
        val += val_step
        res = fmin( fmin_kernel, twoT_guess, args=(val,), xtol=0.005, ftol=0.005, full_output=1 )
        avg_RChi2 = res[1]
        Fx_list.append( [val, avg_RChi2/best_avg_RChi2] )
        Fx_list.sort( key=lambda x: x[0] ) # sort by first element (parameter value)


    # interpolate to find values at threshold
    Fx_array = array( Fx_list )
    splines = cspline1d( Fx_array[:,1] )
    interp_val = linspace( Fx_array[0,0], Fx_array[-1,0], 500 )
    interp_Fx = cspline1d_eval( splines, interp_val, dx=val_step, x0=Fx_array[:,0].min() )
    error_bar = [ interp_val[find(interp_Fx<Fx)[0]], interp_val[find(interp_Fx<Fx)[-1]] ]

    if plotresult:
        fig = figure(1)
        #fig.clf()
        ax_chi = gca()
        #ax_chi = fig.add_subplot(111)
        #ax_chi.cla()
        ax_chi.plot( interp_val, interp_Fx, label=fv )
        ax_chi.plot( interp_val, [Fx]*len(interp_val), '--k' )
        ax_chi.plot( Fx_array[:,0], Fx_array[:,1], 'sk' )
        ax_chi.plot( error_bar, [Fx]*2, '-k', lw=3.0 )

        #ax_chi.set_ylim([0.99, 1.01])
        fig.show()
        fig.canvas.draw()

    return error_bar


if __name__ == "__main__":
    # example usage FROM WITHIN 2nmSiO2 DIRECTORY:
    infile = "cavity_fitresults_760nmIRF_Dispersive_10ctBG_FminAcorr_Aug31"

    fnames_all = []
    fnames_all = glob.glob('wire*.phd')
    fnames_all.sort()
    fnames_all = [ fname for fname in fnames_all if "600nW" in fname ]
    if not sys.argv[1] == 'save':
        fnames_all.append( "offwire01_600nW.phd" )
        fnames_all.append( "offwire02_600nW.phd" )
        fnames_all.append( "offwire03_600nW.phd" )

    if not sys.argv[1].isdigit(): raise ValueError("Need to pass in a wire number...")

    fname = fnames_all[ int(sys.argv[1]) ]
    param = sys.argv[2] # fixed value that we're calculating an errorbar for
    error_bar = get_errorbar( fname, param, plotresult=True )
