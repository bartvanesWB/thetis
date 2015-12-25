# Lock Exchange Test case
# =======================
#
# Solves hydrostatic flow in a closed rectangular channel.
#
# Dianeutral mixing depends on mesh Reynolds number [1]
# Re_h = U dx / nu
# U = 0.5 m/s characteristic velocity ~ 0.5*sqrt(g_h drho/rho_0)
# dx = horizontal mesh size
# nu = background viscosity
#
#
# Smagorinsky factor should be C_s = 1/sqrt(Re_h)
#
# Mesh resolutions:
# - ilicak [1]:  dx =  500 m,  20 layers
# COMODO lock exchange benchmark [2]:
# - coarse:      dx = 2000 m,  10 layers
# - coarse2 (*): dx = 1000 m,  20 layers
# - medium:      dx =  500 m,  40 layers
# - medium2 (*): dx =  250 m,  80 layers
# - fine:        dx =  125 m, 160 layers
# (*) not part of the original benchmark
#
# [1] Ilicak et al. (2012). Spurious dianeutral mixing and the role of
#     momentum closure. Ocean Modelling, 45-46(0):37-58.
#     http://dx.doi.org/10.1016/j.ocemod.2011.10.003
# [2] COMODO Lock Exchange test.
#     http://indi.imag.fr/wordpress/?page_id=446
#
# Tuomas Karna 2015-03-03

from cofs import *

# --- get run params from command line
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('reso_str', type=str,
                    help='resolution string (coarse, medium, fine)')
parser.add_argument('-j', '--jump_diff_factor', type=float, default=1.0,
                    help='factor for jump diff')
parser.add_argument('-l', '--use_limiter', action='store_true',
                    help='use slope limiter for tracers instead of diffusion')
parser.add_argument('-p', '--poly_order', type=int, default=1,
                    help='order of finite element space (0|1)')
parser.add_argument('-m', '--mimetic', action='store_true',
                    help='use mimetic elements for velocity')
parser.add_argument('-Re', '--reynolds_number', type=float, default=2.0,
                    help='mesh Reynolds number for Smagorinsky scheme')
args = parser.parse_args()
if args.use_limiter:
    args.jump_diff_factor = None
args_dict = vars(args)
if commrank == 0:
    print 'Running test case with setup:'
    for k in sorted(args_dict.keys()):
        print ' - {0:15s} : {1:}'.format(k, args_dict[k])

limiter_str = 'limiter' if args.use_limiter else 'jump_diff'+str(args.jump_diff_factor)
space_str = 'RT' if args.mimetic else 'DG'
outputdir = 'out_{:}_p{:}{:}_Re{:}_{:}'.format(args.reso_str, space_str,
                                               args.poly_order,
                                               args.reynolds_number, limiter_str)

outputdir = create_directory(outputdir)
reso_str = args.reso_str
if args.jump_diff_factor is not None:
    args.jump_diff_factor = Constant(args.jump_diff_factor)

# ---

refinement = {'huge': 0.6, 'coarse': 1, 'coarse2': 2, 'medium': 4,
              'medium2': 8, 'fine': 16, 'ilicak': 4}
# set mesh resolution
dx = 2000.0/refinement[reso_str]
layers = int(round(10*refinement[reso_str]))
if reso_str == 'ilicak':
    layers = 20

# generate unit mesh and transform its coords
x_max = 32.0e3
x_min = -32.0e3
n_x = (x_max - x_min)/dx
mesh2d = UnitSquareMesh(n_x, 2)
coords = mesh2d.coordinates
# x in [x_min, x_max], y in [-dx, dx]
coords.dat.data[:, 0] = coords.dat.data[:, 0]*(x_max - x_min) + x_min
coords.dat.data[:, 1] = coords.dat.data[:, 1]*2*dx - dx

print_info('Exporting to '+outputdir)
dt = 75.0/refinement[reso_str]
if reso_str == 'fine':
    dt /= 2.0
t_end = 25 * 3600
t_export = 15*60.0
depth = 20.0

# bathymetry
P1_2d = FunctionSpace(mesh2d, 'CG', 1)
bathymetry2d = Function(P1_2d, name='Bathymetry')
bathymetry2d.assign(depth)

# create solver
solver_obj = solver.FlowSolver(mesh2d, bathymetry2d, layers,
                               order=args.poly_order, mimetic=args.mimetic)
options = solver_obj.options
options.cfl_2d = 1.0
# options.nonlin = False
# options.mimetic = False
options.solve_salt = True
options.solve_vert_diffusion = False
options.use_bottom_friction = False
options.use_ale_moving_mesh = False
# options.use_imex = True
# options.use_semi_implicit_2d = False
# options.use_mode_split = False
options.baroclinic = True
options.uv_lax_friedrichs = Constant(1.0)
options.tracer_lax_friedrichs = Constant(1.0)
options.smagorinsky_factor = Constant(1.0/np.sqrt(args.reynolds_number))
options.salt_jump_diff_factor = args.jump_diff_factor
options.salt_range = Constant(5.0)
options.use_limiter_for_tracers = args.use_limiter
# To keep const grid Re_h, viscosity scales with grid: nu = U dx / Re_h
# options.h_viscosity = Constant(100.0/refinement[reso_str])
options.h_viscosity = Constant(1.0)
options.h_diffusivity = Constant(1.0)
if options.use_mode_split:
    options.dt = dt
options.t_export = t_export
options.t_end = t_end
options.outputdir = outputdir
options.u_advection = Constant(1.0)
options.check_vol_conservation_2d = True
options.check_vol_conservation_3d = True
options.check_salt_conservation = True
options.check_salt_overshoot = True
options.fields_to_export = ['uv_2d', 'elev_2d', 'uv_3d',
                            'w_3d', 'w_mesh_3d', 'salt_3d',
                            'uv_dav_2d', 'uv_dav_3d', 'baroc_head_3d',
                            'baroc_head_2d',
                            'smag_visc_3d', 'salt_jump_diff']
options.fields_to_export_numpy = ['salt_3d']
options.timer_labels = []

solver_obj.create_equations()
salt_init3d = Function(solver_obj.function_spaces.H, name='initial salinity')
# vertical barrier
# salt_init3d.interpolate(Expression(('(x[0] > 0.0) ? 20.0 : 25.0')))
# smooth condition
salt_init3d.interpolate(Expression('22.5 - 2.5*tanh(x[0]/sigma)',
                                   sigma=1000.0))

solver_obj.assign_initial_conditions(salt=salt_init3d)
solver_obj.iterate()