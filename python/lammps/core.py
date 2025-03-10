# ----------------------------------------------------------------------
#   LAMMPS - Large-scale Atomic/Molecular Massively Parallel Simulator
#   http://lammps.sandia.gov, Sandia National Laboratories
#   Steve Plimpton, sjplimp@sandia.gov
#
#   Copyright (2003) Sandia Corporation.  Under the terms of Contract
#   DE-AC04-94AL85000 with Sandia Corporation, the U.S. Government retains
#   certain rights in this software.  This software is distributed under
#   the GNU General Public License.
#
#   See the README file in the top-level LAMMPS directory.
# -------------------------------------------------------------------------
# Python wrapper for the LAMMPS library via ctypes

# for python2/3 compatibility

from __future__ import print_function

import os
import sys
import traceback
import types
import warnings
from ctypes import *
from os.path import dirname,abspath,join
from inspect import getsourcefile

from .constants import *
from .data import *

# -------------------------------------------------------------------------

class MPIAbortException(Exception):
  def __init__(self, message):
    self.message = message

  def __str__(self):
    return repr(self.message)

# -------------------------------------------------------------------------

class ExceptionCheck:
  """Utility class to rethrow LAMMPS C++ exceptions as Python exceptions"""
  def __init__(self, lmp):
    self.lmp = lmp

  def __enter__(self):
    pass

  def __exit__(self, type, value, traceback):
    if self.lmp.has_exceptions and self.lmp.lib.lammps_has_error(self.lmp.lmp):
      raise self.lmp._lammps_exception

# -------------------------------------------------------------------------

class lammps(object):
  """Create an instance of the LAMMPS Python class.

  .. _mpi4py_docs: https://mpi4py.readthedocs.io/

  This is a Python wrapper class that exposes the LAMMPS C-library
  interface to Python.  It either requires that LAMMPS has been compiled
  as shared library which is then dynamically loaded via the ctypes
  Python module or that this module called from a Python function that
  is called from a Python interpreter embedded into a LAMMPS executable,
  for example through the :doc:`python invoke <python>` command.
  When the class is instantiated it calls the :cpp:func:`lammps_open`
  function of the LAMMPS C-library interface, which in
  turn will create an instance of the :cpp:class:`LAMMPS <LAMMPS_NS::LAMMPS>`
  C++ class.  The handle to this C++ class is stored internally
  and automatically passed to the calls to the C library interface.

  :param name: "machine" name of the shared LAMMPS library ("mpi" loads ``liblammps_mpi.so``, "" loads ``liblammps.so``)
  :type  name: string
  :param cmdargs: list of command line arguments to be passed to the :cpp:func:`lammps_open` function.  The executable name is automatically added.
  :type  cmdargs: list
  :param ptr: pointer to a LAMMPS C++ class instance when called from an embedded Python interpreter.  None means load symbols from shared library.
  :type  ptr: pointer
  :param comm: MPI communicator (as provided by `mpi4py <mpi4py_docs_>`_). ``None`` means use ``MPI_COMM_WORLD`` implicitly.
  :type  comm: MPI_Comm
  """

  # -------------------------------------------------------------------------
  # create an instance of LAMMPS

  def __init__(self,name='',cmdargs=None,ptr=None,comm=None):
    self.comm = comm
    self.opened = 0

    # determine module file location

    modpath = dirname(abspath(getsourcefile(lambda:0)))
    # for windows installers the shared library is in a different folder
    winpath = abspath(os.path.join(modpath,'..','..','bin'))
    self.lib = None
    self.lmp = None

    # if a pointer to a LAMMPS object is handed in
    # when being called from a Python interpreter
    # embedded into a LAMMPS executable, all library
    # symbols should already be available so we do not
    # load a shared object.

    try:
      if ptr: self.lib = CDLL("",RTLD_GLOBAL)
    except:
      self.lib = None

    # load liblammps.so unless name is given
    #   if name = "g++", load liblammps_g++.so
    # try loading the LAMMPS shared object from the location
    #   of the lammps package with an absolute path,
    #   so that LD_LIBRARY_PATH does not need to be set for regular install
    # fall back to loading with a relative path,
    #   typically requires LD_LIBRARY_PATH to be set appropriately
    # guess shared library extension based on OS, if not inferred from actual file

    if any([f.startswith('liblammps') and f.endswith('.dylib')
            for f in os.listdir(modpath)]):
      lib_ext = ".dylib"
    elif any([f.startswith('liblammps') and f.endswith('.dll')
              for f in os.listdir(modpath)]):
      lib_ext = ".dll"
    elif os.path.exists(winpath) and any([f.startswith('liblammps') and f.endswith('.dll')
                  for f in os.listdir(winpath)]):
      lib_ext = ".dll"
      modpath = winpath
    else:
      import platform
      if platform.system() == "Darwin":
        lib_ext = ".dylib"
      elif platform.system() == "Windows":
        lib_ext = ".dll"
      else:
        lib_ext = ".so"

    if not self.lib:
      if name:
        libpath = join(modpath,"liblammps_%s" % name + lib_ext)
      else:
        libpath = join(modpath,"liblammps" + lib_ext)
      if not os.path.isfile(libpath):
        if name:
          libpath = "liblammps_%s" % name + lib_ext
        else:
          libpath = "liblammps" + lib_ext
      self.lib = CDLL(libpath,RTLD_GLOBAL)

    # declare all argument and return types for all library methods here.
    # exceptions are where the arguments depend on certain conditions and
    # then are defined where the functions are used.
    self.lib.lammps_extract_setting.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_extract_setting.restype = c_int

    # set default types
    # needed in later declarations
    self.c_bigint = get_ctypes_int(self.extract_setting("bigint"))
    self.c_tagint = get_ctypes_int(self.extract_setting("tagint"))
    self.c_imageint = get_ctypes_int(self.extract_setting("imageint"))

    self.lib.lammps_open.restype = c_void_p
    self.lib.lammps_open_no_mpi.restype = c_void_p
    self.lib.lammps_close.argtypes = [c_void_p]
    self.lib.lammps_free.argtypes = [c_void_p]

    self.lib.lammps_file.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_file.restype = None

    self.lib.lammps_command.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_command.restype = c_char_p
    self.lib.lammps_commands_list.restype = None
    self.lib.lammps_commands_string.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_commands_string.restype = None

    self.lib.lammps_get_natoms.argtypes = [c_void_p]
    self.lib.lammps_get_natoms.restype = c_double
    self.lib.lammps_extract_box.argtypes = \
      [c_void_p,POINTER(c_double),POINTER(c_double),
       POINTER(c_double),POINTER(c_double),POINTER(c_double),
       POINTER(c_int),POINTER(c_int)]
    self.lib.lammps_extract_box.restype = None

    self.lib.lammps_reset_box.argtypes = \
      [c_void_p,POINTER(c_double),POINTER(c_double),c_double,c_double,c_double]
    self.lib.lammps_reset_box.restype = None

    self.lib.lammps_gather_atoms.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_void_p]
    self.lib.lammps_gather_atoms.restype = None

    self.lib.lammps_gather_atoms_concat.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_void_p]
    self.lib.lammps_gather_atoms_concat.restype = None

    self.lib.lammps_gather_atoms_subset.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_int,POINTER(c_int),c_void_p]
    self.lib.lammps_gather_atoms_subset.restype = None

    self.lib.lammps_scatter_atoms.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_void_p]
    self.lib.lammps_scatter_atoms.restype = None

    self.lib.lammps_scatter_atoms_subset.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_int,POINTER(c_int),c_void_p]
    self.lib.lammps_scatter_atoms_subset.restype = None

    self.lib.lammps_gather.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_void_p]
    self.lib.lammps_gather.restype = None

    self.lib.lammps_gather_concat.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_void_p]
    self.lib.lammps_gather_concat.restype = None

    self.lib.lammps_gather_subset.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_int,POINTER(c_int),c_void_p]
    self.lib.lammps_gather_subset.restype = None

    self.lib.lammps_scatter.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_void_p]
    self.lib.lammps_scatter.restype = None

    self.lib.lammps_scatter_subset.argtypes = \
      [c_void_p,c_char_p,c_int,c_int,c_int,POINTER(c_int),c_void_p]
    self.lib.lammps_scatter_subset.restype = None


    self.lib.lammps_find_pair_neighlist.argtypes = [c_void_p, c_char_p, c_int, c_int, c_int]
    self.lib.lammps_find_pair_neighlist.restype  = c_int

    self.lib.lammps_find_fix_neighlist.argtypes = [c_void_p, c_char_p, c_int]
    self.lib.lammps_find_fix_neighlist.restype  = c_int

    self.lib.lammps_find_compute_neighlist.argtypes = [c_void_p, c_char_p, c_int]
    self.lib.lammps_find_compute_neighlist.restype  = c_int

    self.lib.lammps_neighlist_num_elements.argtypes = [c_void_p, c_int]
    self.lib.lammps_neighlist_num_elements.restype  = c_int

    self.lib.lammps_neighlist_element_neighbors.argtypes = [c_void_p, c_int, c_int, POINTER(c_int), POINTER(c_int), POINTER(POINTER(c_int))]
    self.lib.lammps_neighlist_element_neighbors.restype  = None

    self.lib.lammps_is_running.argtypes = [c_void_p]
    self.lib.lammps_is_running.restype = c_int

    self.lib.lammps_force_timeout.argtypes = [c_void_p]

    self.lib.lammps_has_error.argtypes = [c_void_p]
    self.lib.lammps_has_error.restype = c_int

    self.lib.lammps_get_last_error_message.argtypes = [c_void_p, c_char_p, c_int]
    self.lib.lammps_get_last_error_message.restype = c_int

    self.lib.lammps_extract_global.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_extract_global_datatype.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_extract_global_datatype.restype = c_int
    self.lib.lammps_extract_compute.argtypes = [c_void_p, c_char_p, c_int, c_int]

    self.lib.lammps_get_thermo.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_get_thermo.restype = c_double

    self.lib.lammps_encode_image_flags.restype = self.c_imageint

    self.lib.lammps_config_package_name.argtypes = [c_int, c_char_p, c_int]
    self.lib.lammps_config_accelerator.argtypes = [c_char_p, c_char_p, c_char_p]

    self.lib.lammps_set_variable.argtypes = [c_void_p, c_char_p, c_char_p]

    self.lib.lammps_has_style.argtypes = [c_void_p, c_char_p, c_char_p]

    self.lib.lammps_style_count.argtypes = [c_void_p, c_char_p]

    self.lib.lammps_style_name.argtypes = [c_void_p, c_char_p, c_int, c_char_p, c_int]

    self.lib.lammps_has_id.argtypes = [c_void_p, c_char_p, c_char_p]

    self.lib.lammps_id_count.argtypes = [c_void_p, c_char_p]

    self.lib.lammps_id_name.argtypes = [c_void_p, c_char_p, c_int, c_char_p, c_int]

    self.lib.lammps_plugin_count.argtypes = [ ]
    self.lib.lammps_plugin_name.argtypes = [c_int, c_char_p, c_char_p, c_int]

    self.lib.lammps_version.argtypes = [c_void_p]

    self.lib.lammps_get_os_info.argtypes = [c_char_p, c_int]

    self.lib.lammps_get_mpi_comm.argtypes = [c_void_p]

    self.lib.lammps_decode_image_flags.argtypes = [self.c_imageint, POINTER(c_int*3)]

    self.lib.lammps_extract_atom.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_extract_atom_datatype.argtypes = [c_void_p, c_char_p]
    self.lib.lammps_extract_atom_datatype.restype = c_int

    self.lib.lammps_extract_fix.argtypes = [c_void_p, c_char_p, c_int, c_int, c_int, c_int]

    self.lib.lammps_extract_variable.argtypes = [c_void_p, c_char_p, c_char_p]

    # TODO: NOT IMPLEMENTED IN PYTHON WRAPPER
    self.lib.lammps_fix_external_set_energy_global = [c_void_p, c_char_p, c_double]
    self.lib.lammps_fix_external_set_virial_global = [c_void_p, c_char_p, POINTER(c_double)]

    # detect if Python is using a version of mpi4py that can pass communicators
    # only needed if LAMMPS has been compiled with MPI support.
    self.has_mpi4py = False
    if self.has_mpi_support:
      try:
        from mpi4py import __version__ as mpi4py_version
        # tested to work with mpi4py versions 2 and 3
        self.has_mpi4py = mpi4py_version.split('.')[0] in ['2','3']
      except:
        pass

    # if no ptr provided, create an instance of LAMMPS
    #   don't know how to pass an MPI communicator from PyPar
    #   but we can pass an MPI communicator from mpi4py v2.0.0 and later
    #   no_mpi call lets LAMMPS use MPI_COMM_WORLD
    #   cargs = array of C strings from args
    # if ptr, then are embedding Python in LAMMPS input script
    #   ptr is the desired instance of LAMMPS
    #   just convert it to ctypes ptr and store in self.lmp

    if not ptr:

      # with mpi4py v2+, we can pass MPI communicators to LAMMPS
      # need to adjust for type of MPI communicator object
      # allow for int (like MPICH) or void* (like OpenMPI)
      if self.has_mpi_support and self.has_mpi4py:
        from mpi4py import MPI
        self.MPI = MPI

      if comm:
        if not self.has_mpi_support:
          raise Exception('LAMMPS not compiled with real MPI library')
        if not self.has_mpi4py:
          raise Exception('Python mpi4py version is not 2 or 3')
        if self.MPI._sizeof(self.MPI.Comm) == sizeof(c_int):
          MPI_Comm = c_int
        else:
          MPI_Comm = c_void_p

        # Detect whether LAMMPS and mpi4py definitely use different MPI libs
        if sizeof(MPI_Comm) != self.lib.lammps_config_has_mpi_support():
          raise Exception('Inconsistent MPI library in LAMMPS and mpi4py')

        narg = 0
        cargs = None
        if cmdargs:
          cmdargs.insert(0,"lammps")
          narg = len(cmdargs)
          for i in range(narg):
            if type(cmdargs[i]) is str:
              cmdargs[i] = cmdargs[i].encode()
          cargs = (c_char_p*narg)(*cmdargs)
          self.lib.lammps_open.argtypes = [c_int, c_char_p*narg, \
                                           MPI_Comm, c_void_p]
        else:
          self.lib.lammps_open.argtypes = [c_int, c_char_p, \
                                           MPI_Comm, c_void_p]

        self.opened = 1
        comm_ptr = self.MPI._addressof(comm)
        comm_val = MPI_Comm.from_address(comm_ptr)
        self.lmp = c_void_p(self.lib.lammps_open(narg,cargs,comm_val,None))

      else:
        if self.has_mpi4py and self.has_mpi_support:
          self.comm = self.MPI.COMM_WORLD
        self.opened = 1
        if cmdargs:
          cmdargs.insert(0,"lammps")
          narg = len(cmdargs)
          for i in range(narg):
            if type(cmdargs[i]) is str:
              cmdargs[i] = cmdargs[i].encode()
          cargs = (c_char_p*narg)(*cmdargs)
          self.lib.lammps_open_no_mpi.argtypes = [c_int, c_char_p*narg, \
                                                  c_void_p]
          self.lmp = c_void_p(self.lib.lammps_open_no_mpi(narg,cargs,None))
        else:
          self.lib.lammps_open_no_mpi.argtypes = [c_int, c_char_p, c_void_p]
          self.lmp = c_void_p(self.lib.lammps_open_no_mpi(0,None,None))

    else:
      # magic to convert ptr to ctypes ptr
      if sys.version_info >= (3, 0):
        # Python 3 (uses PyCapsule API)
        pythonapi.PyCapsule_GetPointer.restype = c_void_p
        pythonapi.PyCapsule_GetPointer.argtypes = [py_object, c_char_p]
        self.lmp = c_void_p(pythonapi.PyCapsule_GetPointer(ptr, None))
      else:
        # Python 2 (uses PyCObject API)
        pythonapi.PyCObject_AsVoidPtr.restype = c_void_p
        pythonapi.PyCObject_AsVoidPtr.argtypes = [py_object]
        self.lmp = c_void_p(pythonapi.PyCObject_AsVoidPtr(ptr))

    # optional numpy support (lazy loading)
    self._numpy = None

    self._installed_packages = None
    self._available_styles = None

    # check if liblammps version matches the installed python module version
    # but not for in-place usage, i.e. when the version is 0
    import lammps
    if lammps.__version__ > 0 and lammps.__version__ != self.lib.lammps_version(self.lmp):
        raise(AttributeError("LAMMPS Python module installed for LAMMPS version %d, but shared library is version %d" \
                % (lammps.__version__, self.lib.lammps_version(self.lmp))))

    # add way to insert Python callback for fix external
    self.callback = {}
    self.FIX_EXTERNAL_CALLBACK_FUNC = CFUNCTYPE(None, py_object, self.c_bigint, c_int, POINTER(self.c_tagint), POINTER(POINTER(c_double)), POINTER(POINTER(c_double)))
    self.lib.lammps_set_fix_external_callback.argtypes = [c_void_p, c_char_p, self.FIX_EXTERNAL_CALLBACK_FUNC, py_object]
    self.lib.lammps_set_fix_external_callback.restype = None

  # -------------------------------------------------------------------------
  # shut-down LAMMPS instance

  def __del__(self):
    if self.lmp and self.opened:
      self.lib.lammps_close(self.lmp)
      self.opened = 0

  # -------------------------------------------------------------------------

  @property
  def numpy(self):
    """ Return object to access numpy versions of API

    It provides alternative implementations of API functions that
    return numpy arrays instead of ctypes pointers. If numpy is not installed,
    accessing this property will lead to an ImportError.

    :return: instance of numpy wrapper object
    :rtype: numpy_wrapper
    """
    if not self._numpy:
      from .numpy_wrapper import numpy_wrapper
      self._numpy = numpy_wrapper(self)
    return self._numpy

  # -------------------------------------------------------------------------

  def close(self):
    """Explicitly delete a LAMMPS instance through the C-library interface.

    This is a wrapper around the :cpp:func:`lammps_close` function of the C-library interface.
    """
    if self.opened: self.lib.lammps_close(self.lmp)
    self.lmp = None
    self.opened = 0

  # -------------------------------------------------------------------------

  def finalize(self):
    """Shut down the MPI communication through the library interface by calling :cpp:func:`lammps_finalize`.
    """
    if self.opened: self.lib.lammps_close(self.lmp)
    self.lmp = None
    self.opened = 0
    self.lib.lammps_finalize()

  # -------------------------------------------------------------------------

  def version(self):
    """Return a numerical representation of the LAMMPS version in use.

    This is a wrapper around the :cpp:func:`lammps_version` function of the C-library interface.

    :return: version number
    :rtype:  int
    """
    return self.lib.lammps_version(self.lmp)

  # -------------------------------------------------------------------------

  def get_os_info(self):
    """Return a string with information about the OS and compiler runtime

    This is a wrapper around the :cpp:func:`lammps_get_os_info` function of the C-library interface.

    :return: OS info string
    :rtype:  string
    """

    sb = create_string_buffer(512)
    self.lib.lammps_get_os_info(sb,512)
    return sb

  # -------------------------------------------------------------------------

  def get_mpi_comm(self):
    """Get the MPI communicator in use by the current LAMMPS instance

    This is a wrapper around the :cpp:func:`lammps_get_mpi_comm` function
    of the C-library interface.  It will return ``None`` if either the
    LAMMPS library was compiled without MPI support or the mpi4py
    Python module is not available.

    :return: MPI communicator
    :rtype:  MPI_Comm
    """

    if self.has_mpi4py and self.has_mpi_support:
        from mpi4py import MPI
        f_comm = self.lib.lammps_get_mpi_comm(self.lmp)
        c_comm = MPI.Comm.f2py(f_comm)
        return c_comm
    else:
        return None

  # -------------------------------------------------------------------------

  @property
  def _lammps_exception(self):
    sb = create_string_buffer(100)
    error_type = self.lib.lammps_get_last_error_message(self.lmp, sb, 100)
    error_msg = sb.value.decode().strip()

    if error_type == 2:
      return MPIAbortException(error_msg)
    return Exception(error_msg)

  # -------------------------------------------------------------------------

  def file(self, path):
    """Read LAMMPS commands from a file.

    This is a wrapper around the :cpp:func:`lammps_file` function of the C-library interface.
    It will open the file with the name/path `file` and process the LAMMPS commands line by line until
    the end. The function will return when the end of the file is reached.

    :param path: Name of the file/path with LAMMPS commands
    :type path:  string
    """
    if path: path = path.encode()
    else: return

    with ExceptionCheck(self):
      self.lib.lammps_file(self.lmp, path)

  # -------------------------------------------------------------------------

  def command(self,cmd):
    """Process a single LAMMPS input command from a string.

    This is a wrapper around the :cpp:func:`lammps_command`
    function of the C-library interface.

    :param cmd: a single lammps command
    :type cmd:  string
    """
    if cmd: cmd = cmd.encode()
    else: return

    with ExceptionCheck(self):
      self.lib.lammps_command(self.lmp,cmd)

  # -------------------------------------------------------------------------

  def commands_list(self,cmdlist):
    """Process multiple LAMMPS input commands from a list of strings.

    This is a wrapper around the
    :cpp:func:`lammps_commands_list` function of
    the C-library interface.

    :param cmdlist: a single lammps command
    :type cmdlist:  list of strings
    """
    cmds = [x.encode() for x in cmdlist if type(x) is str]
    narg = len(cmdlist)
    args = (c_char_p * narg)(*cmds)
    self.lib.lammps_commands_list.argtypes = [c_void_p, c_int, c_char_p * narg]

    with ExceptionCheck(self):
      self.lib.lammps_commands_list(self.lmp,narg,args)

  # -------------------------------------------------------------------------

  def commands_string(self,multicmd):
    """Process a block of LAMMPS input commands from a string.

    This is a wrapper around the
    :cpp:func:`lammps_commands_string`
    function of the C-library interface.

    :param multicmd: text block of lammps commands
    :type multicmd:  string
    """
    if type(multicmd) is str: multicmd = multicmd.encode()

    with ExceptionCheck(self):
      self.lib.lammps_commands_string(self.lmp,c_char_p(multicmd))

  # -------------------------------------------------------------------------

  def get_natoms(self):
    """Get the total number of atoms in the LAMMPS instance.

    Will be precise up to 53-bit signed integer due to the
    underlying :cpp:func:`lammps_get_natoms` function returning a double.

    :return: number of atoms
    :rtype: int
    """
    return int(self.lib.lammps_get_natoms(self.lmp))

  # -------------------------------------------------------------------------

  def extract_box(self):
    """Extract simulation box parameters

    This is a wrapper around the :cpp:func:`lammps_extract_box` function
    of the C-library interface.  Unlike in the C function, the result is
    returned as a list.

    :return: list of the extracted data: boxlo, boxhi, xy, yz, xz, periodicity, box_change
    :rtype: [ 3*double, 3*double, double, double, 3*int, int]
    """
    boxlo = (3*c_double)()
    boxhi = (3*c_double)()
    xy = c_double()
    yz = c_double()
    xz = c_double()
    periodicity = (3*c_int)()
    box_change = c_int()

    with ExceptionCheck(self):
      self.lib.lammps_extract_box(self.lmp,boxlo,boxhi,
                                  byref(xy),byref(yz),byref(xz),
                                  periodicity,byref(box_change))

    boxlo = boxlo[:3]
    boxhi = boxhi[:3]
    xy = xy.value
    yz = yz.value
    xz = xz.value
    periodicity = periodicity[:3]
    box_change = box_change.value

    return boxlo,boxhi,xy,yz,xz,periodicity,box_change

  # -------------------------------------------------------------------------

  def reset_box(self,boxlo,boxhi,xy,yz,xz):
    """Reset simulation box parameters

    This is a wrapper around the :cpp:func:`lammps_reset_box` function
    of the C-library interface.

    :param boxlo: new lower box boundaries
    :type boxlo: list of 3 floating point numbers
    :param boxhi: new upper box boundaries
    :type boxhi: list of 3 floating point numbers
    :param xy: xy tilt factor
    :type xy: float
    :param yz: yz tilt factor
    :type yz: float
    :param xz: xz tilt factor
    :type xz: float
    """
    cboxlo = (3*c_double)(*boxlo)
    cboxhi = (3*c_double)(*boxhi)
    with ExceptionCheck(self):
      self.lib.lammps_reset_box(self.lmp,cboxlo,cboxhi,xy,yz,xz)

  # -------------------------------------------------------------------------

  def get_thermo(self,name):
    """Get current value of a thermo keyword

    This is a wrapper around the :cpp:func:`lammps_get_thermo`
    function of the C-library interface.

    :param name: name of thermo keyword
    :type name: string
    :return: value of thermo keyword
    :rtype: double or None
    """
    if name: name = name.encode()
    else: return None

    with ExceptionCheck(self):
      return self.lib.lammps_get_thermo(self.lmp,name)

  # -------------------------------------------------------------------------

  def extract_setting(self, name):
    """Query LAMMPS about global settings that can be expressed as an integer.

    This is a wrapper around the :cpp:func:`lammps_extract_setting`
    function of the C-library interface.  Its documentation includes
    a list of the supported keywords.

    :param name: name of the setting
    :type name:  string
    :return: value of the setting
    :rtype: int
    """
    if name: name = name.encode()
    else: return None
    return int(self.lib.lammps_extract_setting(self.lmp,name))

  # -------------------------------------------------------------------------
  # extract global info datatype

  def extract_global_datatype(self, name):
    """Retrieve global property datatype from LAMMPS

    This is a wrapper around the :cpp:func:`lammps_extract_global_datatype`
    function of the C-library interface. Its documentation includes a
    list of the supported keywords.
    This function returns ``None`` if the keyword is not
    recognized. Otherwise it will return a positive integer value that
    corresponds to one of the :ref:`data type <py_datatype_constants>`
    constants define in the :py:mod:`lammps` module.

    :param name: name of the property
    :type name:  string
    :return: data type of global property, see :ref:`py_datatype_constants`
    :rtype: int
    """
    if name: name = name.encode()
    else: return None
    return self.lib.lammps_extract_global_datatype(self.lmp, name)

  # -------------------------------------------------------------------------
  # extract global info

  def extract_global(self, name, dtype=LAMMPS_AUTODETECT):
    """Query LAMMPS about global settings of different types.

    This is a wrapper around the :cpp:func:`lammps_extract_global` function
    of the C-library interface.  Since there are no pointers in Python, this
    method will - unlike the C function - return the value or a list of
    values.  The :cpp:func:`lammps_extract_global` documentation includes a
    list of the supported keywords and their data types.
    Since Python needs to know the data type to be able to interpret
    the result, by default, this function will try to auto-detect the data type
    by asking the library. You can also force a specific data type.  For that
    purpose the :py:mod:`lammps` module contains :ref:`data type <py_datatype_constants>`
    constants. This function returns ``None`` if either the keyword is not recognized,
    or an invalid data type constant is used.

    :param name: name of the property
    :type name:  string
    :param dtype: data type of the returned data (see :ref:`py_datatype_constants`)
    :type dtype:  int, optional
    :return: value of the property or list of values or None
    :rtype: int, float, list, or NoneType
    """

    if dtype == LAMMPS_AUTODETECT:
      dtype = self.extract_global_datatype(name)

    # set length of vector for items that are not a scalar
    vec_dict = { 'boxlo':3, 'boxhi':3, 'sublo':3, 'subhi':3,
                 'sublo_lambda':3, 'subhi_lambda':3, 'periodicity':3 }
    if name in vec_dict:
      veclen = vec_dict[name]
    elif name == 'respa_dt':
      veclen = self.extract_global('respa_levels',LAMMPS_INT)
    else:
      veclen = 1

    if name: name = name.encode()
    else: return None

    if dtype == LAMMPS_INT:
      self.lib.lammps_extract_global.restype = POINTER(c_int32)
      target_type = int
    elif dtype == LAMMPS_INT64:
      self.lib.lammps_extract_global.restype = POINTER(c_int64)
      target_type = int
    elif dtype == LAMMPS_DOUBLE:
      self.lib.lammps_extract_global.restype = POINTER(c_double)
      target_type = float
    elif dtype == LAMMPS_STRING:
      self.lib.lammps_extract_global.restype = c_char_p

    ptr = self.lib.lammps_extract_global(self.lmp, name)
    if ptr:
      if dtype == LAMMPS_STRING:
        return ptr.decode('utf-8')
      if veclen > 1:
        result = []
        for i in range(0,veclen):
          result.append(target_type(ptr[i]))
        return result
      else: return target_type(ptr[0])
    return None

  # -------------------------------------------------------------------------
  # extract per-atom info datatype

  def extract_atom_datatype(self, name):
    """Retrieve per-atom property datatype from LAMMPS

    This is a wrapper around the :cpp:func:`lammps_extract_atom_datatype`
    function of the C-library interface. Its documentation includes a
    list of the supported keywords.
    This function returns ``None`` if the keyword is not
    recognized. Otherwise it will return an integer value that
    corresponds to one of the :ref:`data type <py_datatype_constants>` constants
    defined in the :py:mod:`lammps` module.

    :param name: name of the property
    :type name:  string
    :return: data type of per-atom property (see :ref:`py_datatype_constants`)
    :rtype: int
    """
    if name: name = name.encode()
    else: return None
    return self.lib.lammps_extract_atom_datatype(self.lmp, name)

  # -------------------------------------------------------------------------
  # extract per-atom info

  def extract_atom(self, name, dtype=LAMMPS_AUTODETECT):
    """Retrieve per-atom properties from LAMMPS

    This is a wrapper around the :cpp:func:`lammps_extract_atom`
    function of the C-library interface. Its documentation includes a
    list of the supported keywords and their data types.
    Since Python needs to know the data type to be able to interpret
    the result, by default, this function will try to auto-detect the data type
    by asking the library. You can also force a specific data type by setting ``dtype``
    to one of the :ref:`data type <py_datatype_constants>` constants defined in the
    :py:mod:`lammps` module.
    This function returns ``None`` if either the keyword is not
    recognized, or an invalid data type constant is used.

    .. note::

       While the returned arrays of per-atom data are dimensioned
       for the range [0:nmax] - as is the underlying storage -
       the data is usually only valid for the range of [0:nlocal],
       unless the property of interest is also updated for ghost
       atoms.  In some cases, this depends on a LAMMPS setting, see
       for example :doc:`comm_modify vel yes <comm_modify>`.

    :param name: name of the property
    :type name:  string
    :param dtype: data type of the returned data (see :ref:`py_datatype_constants`)
    :type dtype:  int, optional
    :return: requested data or ``None``
    :rtype: ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)),
            ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.POINTER(ctypes.c_int64)),
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.POINTER(ctypes.c_double)),
            or NoneType
    """
    if dtype == LAMMPS_AUTODETECT:
      dtype = self.extract_atom_datatype(name)

    if name: name = name.encode()
    else: return None

    if dtype == LAMMPS_INT:
      self.lib.lammps_extract_atom.restype = POINTER(c_int32)
    elif dtype == LAMMPS_INT_2D:
      self.lib.lammps_extract_atom.restype = POINTER(POINTER(c_int32))
    elif dtype == LAMMPS_DOUBLE:
      self.lib.lammps_extract_atom.restype = POINTER(c_double)
    elif dtype == LAMMPS_DOUBLE_2D:
      self.lib.lammps_extract_atom.restype = POINTER(POINTER(c_double))
    elif dtype == LAMMPS_INT64:
      self.lib.lammps_extract_atom.restype = POINTER(c_int64)
    elif dtype == LAMMPS_INT64_2D:
      self.lib.lammps_extract_atom.restype = POINTER(POINTER(c_int64))
    else: return None

    ptr = self.lib.lammps_extract_atom(self.lmp, name)
    if ptr: return ptr
    else:   return None


  # -------------------------------------------------------------------------

  def extract_compute(self,id,style,type):
    """Retrieve data from a LAMMPS compute

    This is a wrapper around the :cpp:func:`lammps_extract_compute`
    function of the C-library interface.
    This function returns ``None`` if either the compute id is not
    recognized, or an invalid combination of :ref:`style <py_style_constants>`
    and :ref:`type <py_type_constants>` constants is used. The
    names and functionality of the constants are the same as for
    the corresponding C-library function.  For requests to return
    a scalar or a size, the value is returned, otherwise a pointer.

    :param id: compute ID
    :type id:  string
    :param style: style of the data retrieve (global, atom, or local), see :ref:`py_style_constants`
    :type style:  int
    :param type: type or size of the returned data (scalar, vector, or array), see :ref:`py_type_constants`
    :type type:  int
    :return: requested data as scalar, pointer to 1d or 2d double array, or None
    :rtype: c_double, ctypes.POINTER(c_double), ctypes.POINTER(ctypes.POINTER(c_double)), or NoneType
    """
    if id: id = id.encode()
    else: return None

    if type == LMP_TYPE_SCALAR:
      if style == LMP_STYLE_GLOBAL:
        self.lib.lammps_extract_compute.restype = POINTER(c_double)
        with ExceptionCheck(self):
          ptr = self.lib.lammps_extract_compute(self.lmp,id,style,type)
        return ptr[0]
      elif style == LMP_STYLE_ATOM:
        return None
      elif style == LMP_STYLE_LOCAL:
        self.lib.lammps_extract_compute.restype = POINTER(c_int)
        with ExceptionCheck(self):
          ptr = self.lib.lammps_extract_compute(self.lmp,id,style,type)
        return ptr[0]

    elif type == LMP_TYPE_VECTOR:
      self.lib.lammps_extract_compute.restype = POINTER(c_double)
      with ExceptionCheck(self):
        ptr = self.lib.lammps_extract_compute(self.lmp,id,style,type)
      return ptr

    elif type == LMP_TYPE_ARRAY:
      self.lib.lammps_extract_compute.restype = POINTER(POINTER(c_double))
      with ExceptionCheck(self):
        ptr = self.lib.lammps_extract_compute(self.lmp,id,style,type)
      return ptr

    elif type == LMP_SIZE_COLS:
      if style == LMP_STYLE_GLOBAL  \
         or style == LMP_STYLE_ATOM \
         or style == LMP_STYLE_LOCAL:
        self.lib.lammps_extract_compute.restype = POINTER(c_int)
        with ExceptionCheck(self):
          ptr = self.lib.lammps_extract_compute(self.lmp,id,style,type)
        return ptr[0]

    elif type == LMP_SIZE_VECTOR or type == LMP_SIZE_ROWS:
      if style == LMP_STYLE_GLOBAL  \
         or style == LMP_STYLE_LOCAL:
        self.lib.lammps_extract_compute.restype = POINTER(c_int)
        with ExceptionCheck(self):
          ptr = self.lib.lammps_extract_compute(self.lmp,id,style,type)
        return ptr[0]

    return None

  # -------------------------------------------------------------------------
  # extract fix info
  # in case of global data, free memory for 1 double via lammps_free()
  # double was allocated by library interface function

  def extract_fix(self,id,style,type,nrow=0,ncol=0):
    """Retrieve data from a LAMMPS fix

    This is a wrapper around the :cpp:func:`lammps_extract_fix`
    function of the C-library interface.
    This function returns ``None`` if either the fix id is not
    recognized, or an invalid combination of :ref:`style <py_style_constants>`
    and :ref:`type <py_type_constants>` constants is used. The
    names and functionality of the constants are the same as for
    the corresponding C-library function.  For requests to return
    a scalar or a size, the value is returned, also when accessing
    global vectors or arrays, otherwise a pointer.

    :param id: fix ID
    :type id:  string
    :param style: style of the data retrieve (global, atom, or local), see :ref:`py_style_constants`
    :type style:  int
    :param type: type or size of the returned data (scalar, vector, or array), see :ref:`py_type_constants`
    :type type:  int
    :param nrow: index of global vector element or row index of global array element
    :type nrow:  int
    :param ncol: column index of global array element
    :type ncol:  int
    :return: requested data or None
    :rtype: c_double, ctypes.POINTER(c_double), ctypes.POINTER(ctypes.POINTER(c_double)), or NoneType

    """
    if id: id = id.encode()
    else: return None

    if style == LMP_STYLE_GLOBAL:
      if type in (LMP_TYPE_SCALAR, LMP_TYPE_VECTOR, LMP_TYPE_ARRAY):
        self.lib.lammps_extract_fix.restype = POINTER(c_double)
        with ExceptionCheck(self):
          ptr = self.lib.lammps_extract_fix(self.lmp,id,style,type,nrow,ncol)
        result = ptr[0]
        self.lib.lammps_free(ptr)
        return result
      elif type in (LMP_SIZE_VECTOR, LMP_SIZE_ROWS, LMP_SIZE_COLS):
        self.lib.lammps_extract_fix.restype = POINTER(c_int)
        with ExceptionCheck(self):
          ptr = self.lib.lammps_extract_fix(self.lmp,id,style,type,nrow,ncol)
        return ptr[0]
      else:
        return None

    elif style == LMP_STYLE_ATOM:
      if type == LMP_TYPE_VECTOR:
        self.lib.lammps_extract_fix.restype = POINTER(c_double)
      elif type == LMP_TYPE_ARRAY:
        self.lib.lammps_extract_fix.restype = POINTER(POINTER(c_double))
      elif type == LMP_SIZE_COLS:
        self.lib.lammps_extract_fix.restype = POINTER(c_int)
      else:
        return None
      with ExceptionCheck(self):
        ptr = self.lib.lammps_extract_fix(self.lmp,id,style,type,nrow,ncol)
      if type == LMP_SIZE_COLS:
        return ptr[0]
      else:
        return ptr

    elif style == LMP_STYLE_LOCAL:
      if type == LMP_TYPE_VECTOR:
        self.lib.lammps_extract_fix.restype = POINTER(c_double)
      elif type == LMP_TYPE_ARRAY:
        self.lib.lammps_extract_fix.restype = POINTER(POINTER(c_double))
      elif type in (LMP_TYPE_SCALAR, LMP_SIZE_VECTOR, LMP_SIZE_ROWS, LMP_SIZE_COLS):
        self.lib.lammps_extract_fix.restype = POINTER(c_int)
      else:
        return None
      with ExceptionCheck(self):
        ptr = self.lib.lammps_extract_fix(self.lmp,id,style,type,nrow,ncol)
      if type in (LMP_TYPE_VECTOR, LMP_TYPE_ARRAY):
        return ptr
      else:
        return ptr[0]
    else:
      return None

  # -------------------------------------------------------------------------
  # extract variable info
  # free memory for 1 double or 1 vector of doubles via lammps_free()
  # for vector, must copy nlocal returned values to local c_double vector
  # memory was allocated by library interface function

  def extract_variable(self, name, group=None, vartype=LMP_VAR_EQUAL):
    """ Evaluate a LAMMPS variable and return its data

    This function is a wrapper around the function
    :cpp:func:`lammps_extract_variable` of the C-library interface,
    evaluates variable name and returns a copy of the computed data.
    The memory temporarily allocated by the C-interface is deleted
    after the data is copied to a Python variable or list.
    The variable must be either an equal-style (or equivalent)
    variable or an atom-style variable. The variable type has to
    provided as ``vartype`` parameter which may be one of two constants:
    ``LMP_VAR_EQUAL`` or ``LMP_VAR_ATOM``; it defaults to
    equal-style variables.
    The group parameter is only used for atom-style variables and
    defaults to the group "all" if set to ``None``, which is the default.

    :param name: name of the variable to execute
    :type name: string
    :param group: name of group for atom-style variable
    :type group: string, only for atom-style variables
    :param vartype: type of variable, see :ref:`py_vartype_constants`
    :type vartype: int
    :return: the requested data
    :rtype: c_double, (c_double), or NoneType
    """
    if name: name = name.encode()
    else: return None
    if group: group = group.encode()
    if vartype == LMP_VAR_EQUAL:
      self.lib.lammps_extract_variable.restype = POINTER(c_double)
      with ExceptionCheck(self):
        ptr = self.lib.lammps_extract_variable(self.lmp,name,group)
      if ptr: result = ptr[0]
      else: return None
      self.lib.lammps_free(ptr)
      return result
    elif vartype == LMP_VAR_ATOM:
      nlocal = self.extract_global("nlocal")
      result = (c_double*nlocal)()
      self.lib.lammps_extract_variable.restype = POINTER(c_double)
      with ExceptionCheck(self):
        ptr = self.lib.lammps_extract_variable(self.lmp,name,group)
      if ptr:
        for i in range(nlocal): result[i] = ptr[i]
        self.lib.lammps_free(ptr)
      else: return None
      return result
    return None

  # -------------------------------------------------------------------------

  def set_variable(self,name,value):
    """Set a new value for a LAMMPS string style variable

    This is a wrapper around the :cpp:func:`lammps_set_variable`
    function of the C-library interface.

    :param name: name of the variable
    :type name: string
    :param value: new variable value
    :type value: any. will be converted to a string
    :return: either 0 on success or -1 on failure
    :rtype: int
    """
    if name: name = name.encode()
    else: return -1
    if value: value = str(value).encode()
    else: return -1
    with ExceptionCheck(self):
      return self.lib.lammps_set_variable(self.lmp,name,value)

  # -------------------------------------------------------------------------

  # return vector of atom properties gathered across procs
  # 3 variants to match src/library.cpp
  # name = atom property recognized by LAMMPS in atom->extract()
  # type = 0 for integer values, 1 for double values
  # count = number of per-atom valus, 1 for type or charge, 3 for x or f
  # returned data is a 1d vector - doc how it is ordered?
  # NOTE: need to insure are converting to/from correct Python type
  #   e.g. for Python list or NumPy or ctypes

  def gather_atoms(self,name,type,count):
    if name: name = name.encode()
    natoms = self.get_natoms()
    with ExceptionCheck(self):
      if type == 0:
        data = ((count*natoms)*c_int)()
        self.lib.lammps_gather_atoms(self.lmp,name,type,count,data)
      elif type == 1:
        data = ((count*natoms)*c_double)()
        self.lib.lammps_gather_atoms(self.lmp,name,type,count,data)
      else:
        return None
    return data

  # -------------------------------------------------------------------------

  def gather_atoms_concat(self,name,type,count):
    if name: name = name.encode()
    natoms = self.get_natoms()
    with ExceptionCheck(self):
      if type == 0:
        data = ((count*natoms)*c_int)()
        self.lib.lammps_gather_atoms_concat(self.lmp,name,type,count,data)
      elif type == 1:
        data = ((count*natoms)*c_double)()
        self.lib.lammps_gather_atoms_concat(self.lmp,name,type,count,data)
      else:
          return None
    return data

  def gather_atoms_subset(self,name,type,count,ndata,ids):
    if name: name = name.encode()
    with ExceptionCheck(self):
      if type == 0:
        data = ((count*ndata)*c_int)()
        self.lib.lammps_gather_atoms_subset(self.lmp,name,type,count,ndata,ids,data)
      elif type == 1:
        data = ((count*ndata)*c_double)()
        self.lib.lammps_gather_atoms_subset(self.lmp,name,type,count,ndata,ids,data)
      else:
        return None
    return data

  # -------------------------------------------------------------------------

  # scatter vector of atom properties across procs
  # 2 variants to match src/library.cpp
  # name = atom property recognized by LAMMPS in atom->extract()
  # type = 0 for integer values, 1 for double values
  # count = number of per-atom valus, 1 for type or charge, 3 for x or f
  # assume data is of correct type and length, as created by gather_atoms()
  # NOTE: need to insure are converting to/from correct Python type
  #   e.g. for Python list or NumPy or ctypes

  def scatter_atoms(self,name,type,count,data):
    if name: name = name.encode()
    with ExceptionCheck(self):
      self.lib.lammps_scatter_atoms(self.lmp,name,type,count,data)

  # -------------------------------------------------------------------------

  def scatter_atoms_subset(self,name,type,count,ndata,ids,data):
    if name: name = name.encode()
    with ExceptionCheck(self):
      self.lib.lammps_scatter_atoms_subset(self.lmp,name,type,count,ndata,ids,data)

  # return vector of atom/compute/fix properties gathered across procs
  # 3 variants to match src/library.cpp
  # name = atom property recognized by LAMMPS in atom->extract()
  # type = 0 for integer values, 1 for double values
  # count = number of per-atom valus, 1 for type or charge, 3 for x or f
  # returned data is a 1d vector - doc how it is ordered?
  # NOTE: need to insure are converting to/from correct Python type
  #   e.g. for Python list or NumPy or ctypes
  def gather(self,name,type,count):
    if name: name = name.encode()
    natoms = self.get_natoms()
    with ExceptionCheck(self):
      if type == 0:
        data = ((count*natoms)*c_int)()
        self.lib.lammps_gather(self.lmp,name,type,count,data)
      elif type == 1:
        data = ((count*natoms)*c_double)()
        self.lib.lammps_gather(self.lmp,name,type,count,data)
      else:
        return None
    return data

  def gather_concat(self,name,type,count):
    if name: name = name.encode()
    natoms = self.get_natoms()
    with ExceptionCheck(self):
      if type == 0:
        data = ((count*natoms)*c_int)()
        self.lib.lammps_gather_concat(self.lmp,name,type,count,data)
      elif type == 1:
        data = ((count*natoms)*c_double)()
        self.lib.lammps_gather_concat(self.lmp,name,type,count,data)
      else:
        return None
    return data

  def gather_subset(self,name,type,count,ndata,ids):
    if name: name = name.encode()
    with ExceptionCheck(self):
      if type == 0:
        data = ((count*ndata)*c_int)()
        self.lib.lammps_gather_subset(self.lmp,name,type,count,ndata,ids,data)
      elif type == 1:
        data = ((count*ndata)*c_double)()
        self.lib.lammps_gather_subset(self.lmp,name,type,count,ndata,ids,data)
      else:
        return None
    return data

  # scatter vector of atom/compute/fix properties across procs
  # 2 variants to match src/library.cpp
  # name = atom property recognized by LAMMPS in atom->extract()
  # type = 0 for integer values, 1 for double values
  # count = number of per-atom valus, 1 for type or charge, 3 for x or f
  # assume data is of correct type and length, as created by gather_atoms()
  # NOTE: need to insure are converting to/from correct Python type
  #   e.g. for Python list or NumPy or ctypes

  def scatter(self,name,type,count,data):
    if name: name = name.encode()
    with ExceptionCheck(self):
      self.lib.lammps_scatter(self.lmp,name,type,count,data)

  def scatter_subset(self,name,type,count,ndata,ids,data):
    if name: name = name.encode()
    with ExceptionCheck(self):
      self.lib.lammps_scatter_subset(self.lmp,name,type,count,ndata,ids,data)

   # -------------------------------------------------------------------------

  def encode_image_flags(self,ix,iy,iz):
    """ convert 3 integers with image flags for x-, y-, and z-direction
    into a single integer like it is used internally in LAMMPS

    This method is a wrapper around the :cpp:func:`lammps_encode_image_flags`
    function of library interface.

    :param ix: x-direction image flag
    :type  ix: int
    :param iy: y-direction image flag
    :type  iy: int
    :param iz: z-direction image flag
    :type  iz: int
    :return: encoded image flags
    :rtype: lammps.c_imageint
    """
    return self.lib.lammps_encode_image_flags(ix,iy,iz)

  # -------------------------------------------------------------------------

  def decode_image_flags(self,image):
    """ Convert encoded image flag integer into list of three regular integers.

    This method is a wrapper around the :cpp:func:`lammps_decode_image_flags`
    function of library interface.

    :param image: encoded image flags
    :type image:  lammps.c_imageint
    :return: list of three image flags in x-, y-, and z- direction
    :rtype: list of 3 int
    """

    flags = (c_int*3)()
    self.lib.lammps_decode_image_flags(image,byref(flags))

    return [int(i) for i in flags]

  # -------------------------------------------------------------------------

  # create N atoms on all procs
  # N = global number of atoms
  # id = ID of each atom (optional, can be None)
  # type = type of each atom (1 to Ntypes) (required)
  # x = coords of each atom as (N,3) array (required)
  # v = velocity of each atom as (N,3) array (optional, can be None)
  # NOTE: how could we insure are passing correct type to LAMMPS
  #   e.g. for Python list or NumPy, etc
  #   ditto for gather_atoms() above

  def create_atoms(self,n,id,type,x,v=None,image=None,shrinkexceed=False):
    """
    Create N atoms from list of coordinates and properties

    This function is a wrapper around the :cpp:func:`lammps_create_atoms`
    function of the C-library interface, and the behavior is similar except
    that the *v*, *image*, and *shrinkexceed* arguments are optional and
    default to *None*, *None*, and *False*, respectively. With none being
    equivalent to a ``NULL`` pointer in C.

    The lists of coordinates, types, atom IDs, velocities, image flags can
    be provided in any format that may be converted into the required
    internal data types.  Also the list may contain more than *N* entries,
    but not fewer.  In the latter case, the function will return without
    attempting to create atoms.  You may use the :py:func:`encode_image_flags
    <lammps.encode_image_flags>` method to properly combine three integers
    with image flags into a single integer.

    :param n: number of atoms for which data is provided
    :type n: int
    :param id: list of atom IDs with at least n elements or None
    :type id: list of lammps.tagint
    :param type: list of atom types
    :type type: list of int
    :param x: list of coordinates for x-, y-, and z (flat list of 3n entries)
    :type x: list of float
    :param v: list of velocities for x-, y-, and z (flat list of 3n entries) or None (optional)
    :type v: list of float
    :param image: list of encoded image flags (optional)
    :type image: list of lammps.imageint
    :param shrinkexceed: whether to expand shrink-wrap boundaries if atoms are outside the box (optional)
    :type shrinkexceed: bool
    :return: number of atoms created. 0 if insufficient or invalid data
    :rtype: int
    """
    if id:
      id_lmp = (self.c_tagint*n)()
      try:
        id_lmp[:] = id[0:n]
      except:
        return 0
    else:
      id_lmp = None

    type_lmp = (c_int*n)()
    try:
      type_lmp[:] = type[0:n]
    except:
      return 0

    three_n = 3*n
    x_lmp = (c_double*three_n)()
    try:
      x_lmp[:] = x[0:three_n]
    except:
      return 0

    if v:
      v_lmp = (c_double*(three_n))()
      try:
        v_lmp[:] = v[0:three_n]
      except:
        return 0
    else:
      v_lmp = None

    if image:
      img_lmp = (self.c_imageint*n)()
      try:
        img_lmp[:] = image[0:n]
      except:
        return 0
    else:
      img_lmp = None

    if shrinkexceed:
      se_lmp = 1
    else:
      se_lmp = 0

    self.lib.lammps_create_atoms.argtypes = [c_void_p, c_int, POINTER(self.c_tagint*n),
                                     POINTER(c_int*n), POINTER(c_double*three_n),
                                     POINTER(c_double*three_n),
                                     POINTER(self.c_imageint*n), c_int]
    with ExceptionCheck(self):
      return self.lib.lammps_create_atoms(self.lmp, n, id_lmp, type_lmp, x_lmp, v_lmp, img_lmp, se_lmp)

  # -------------------------------------------------------------------------

  @property
  def has_mpi_support(self):
    """ Report whether the LAMMPS shared library was compiled with a
    real MPI library or in serial.

    This is a wrapper around the :cpp:func:`lammps_config_has_mpi_support`
    function of the library interface.

    :return: False when compiled with MPI STUBS, otherwise True
    :rtype: bool
    """
    return self.lib.lammps_config_has_mpi_support() != 0

  # -------------------------------------------------------------------------

  @property
  def is_running(self):
    """ Report whether being called from a function during a run or a minimization

    Various LAMMPS commands must not be called during an ongoing
    run or minimization.  This property allows to check for that.
    This is a wrapper around the :cpp:func:`lammps_is_running`
    function of the library interface.

    .. versionadded:: 9Oct2020

    :return: True when called during a run otherwise false
    :rtype: bool
    """
    return self.lib.lammps_is_running(self.lmp) == 1

  # -------------------------------------------------------------------------

  def force_timeout(self):
    """ Trigger an immediate timeout, i.e. a "soft stop" of a run.

    This function allows to cleanly stop an ongoing run or minimization
    at the next loop iteration.
    This is a wrapper around the :cpp:func:`lammps_force_timeout`
    function of the library interface.

    .. versionadded:: 9Oct2020
    """
    self.lib.lammps_force_timeout(self.lmp)

  # -------------------------------------------------------------------------

  @property
  def has_exceptions(self):
    """ Report whether the LAMMPS shared library was compiled with C++
    exceptions handling enabled

    This is a wrapper around the :cpp:func:`lammps_config_has_exceptions`
    function of the library interface.

    :return: state of C++ exception support
    :rtype: bool
    """
    return self.lib.lammps_config_has_exceptions() != 0

  # -------------------------------------------------------------------------

  @property
  def has_gzip_support(self):
    """ Report whether the LAMMPS shared library was compiled with support
    for reading and writing compressed files through ``gzip``.

    This is a wrapper around the :cpp:func:`lammps_config_has_gzip_support`
    function of the library interface.

    :return: state of gzip support
    :rtype: bool
    """
    return self.lib.lammps_config_has_gzip_support() != 0

  # -------------------------------------------------------------------------

  @property
  def has_png_support(self):
    """ Report whether the LAMMPS shared library was compiled with support
    for writing images in PNG format.

    This is a wrapper around the :cpp:func:`lammps_config_has_png_support`
    function of the library interface.

    :return: state of PNG support
    :rtype: bool
    """
    return self.lib.lammps_config_has_png_support() != 0

  # -------------------------------------------------------------------------

  @property
  def has_jpeg_support(self):
    """ Report whether the LAMMPS shared library was compiled with support
    for writing images in JPEG format.

    This is a wrapper around the :cpp:func:`lammps_config_has_jpeg_support`
    function of the library interface.

    :return: state of JPEG support
    :rtype: bool
    """
    return self.lib.lammps_config_has_jpeg_support() != 0

  # -------------------------------------------------------------------------

  @property
  def has_ffmpeg_support(self):
    """ State of support for writing movies with ``ffmpeg`` in the LAMMPS shared library

    This is a wrapper around the :cpp:func:`lammps_config_has_ffmpeg_support`
    function of the library interface.

    :return: state of ffmpeg support
    :rtype: bool
    """
    return self.lib.lammps_config_has_ffmpeg_support() != 0

  # -------------------------------------------------------------------------

  @property
  def accelerator_config(self):
    """ Return table with available accelerator configuration settings.

    This is a wrapper around the :cpp:func:`lammps_config_accelerator`
    function of the library interface which loops over all known packages
    and categories and returns enabled features as a nested dictionary
    with all enabled settings as list of strings.

    :return: nested dictionary with all known enabled settings as list of strings
    :rtype: dictionary
    """

    result = {}
    for p in ['GPU', 'KOKKOS', 'USER-INTEL', 'USER-OMP']:
      result[p] = {}
      c = 'api'
      result[p][c] = []
      for s in ['cuda', 'hip', 'phi', 'pthreads', 'opencl', 'openmp', 'serial']:
        if self.lib.lammps_config_accelerator(p.encode(),c.encode(),s.encode()):
          result[p][c].append(s)
      c = 'precision'
      result[p][c] = []
      for s in ['double', 'mixed', 'single']:
        if self.lib.lammps_config_accelerator(p.encode(),c.encode(),s.encode()):
          result[p][c].append(s)
    return result

  # -------------------------------------------------------------------------

  @property
  def installed_packages(self):
    """ List of the names of enabled packages in the LAMMPS shared library

    This is a wrapper around the functions :cpp:func:`lammps_config_package_count`
    and :cpp:func`lammps_config_package_name` of the library interface.

    :return
    """
    if self._installed_packages is None:
      self._installed_packages = []
      npackages = self.lib.lammps_config_package_count()
      sb = create_string_buffer(100)
      for idx in range(npackages):
        self.lib.lammps_config_package_name(idx, sb, 100)
        self._installed_packages.append(sb.value.decode())
    return self._installed_packages

  # -------------------------------------------------------------------------

  def has_style(self, category, name):
    """Returns whether a given style name is available in a given category

    This is a wrapper around the function :cpp:func:`lammps_has_style`
    of the library interface.

    :param category: name of category
    :type  category: string
    :param name: name of the style
    :type  name: string

    :return: true if style is available in given category
    :rtype:  bool
    """
    return self.lib.lammps_has_style(self.lmp, category.encode(), name.encode()) != 0

  # -------------------------------------------------------------------------

  def available_styles(self, category):
    """Returns a list of styles available for a given category

    This is a wrapper around the functions :cpp:func:`lammps_style_count()`
    and :cpp:func:`lammps_style_name()` of the library interface.

    :param category: name of category
    :type  category: string

    :return: list of style names in given category
    :rtype:  list
    """
    if self._available_styles is None:
      self._available_styles = {}

    if category not in self._available_styles:
      self._available_styles[category] = []
      with ExceptionCheck(self):
        nstyles = self.lib.lammps_style_count(self.lmp, category.encode())
      sb = create_string_buffer(100)
      for idx in range(nstyles):
        with ExceptionCheck(self):
          self.lib.lammps_style_name(self.lmp, category.encode(), idx, sb, 100)
        self._available_styles[category].append(sb.value.decode())
    return self._available_styles[category]

  # -------------------------------------------------------------------------

  def has_id(self, category, name):
    """Returns whether a given ID name is available in a given category

    This is a wrapper around the function :cpp:func:`lammps_has_id`
    of the library interface.

    .. versionadded:: 9Oct2020

    :param category: name of category
    :type  category: string
    :param name: name of the ID
    :type  name: string

    :return: true if ID is available in given category
    :rtype:  bool
    """
    return self.lib.lammps_has_id(self.lmp, category.encode(), name.encode()) != 0

  # -------------------------------------------------------------------------

  def available_ids(self, category):
    """Returns a list of IDs available for a given category

    This is a wrapper around the functions :cpp:func:`lammps_id_count()`
    and :cpp:func:`lammps_id_name()` of the library interface.

    .. versionadded:: 9Oct2020

    :param category: name of category
    :type  category: string

    :return: list of id names in given category
    :rtype:  list
    """

    categories = ['compute','dump','fix','group','molecule','region','variable']
    available_ids = []
    if category in categories:
      num = self.lib.lammps_id_count(self.lmp, category.encode())
      sb = create_string_buffer(100)
      for idx in range(num):
        self.lib.lammps_id_name(self.lmp, category.encode(), idx, sb, 100)
        available_ids.append(sb.value.decode())
    return available_ids

  # -------------------------------------------------------------------------

  def available_plugins(self, category):
    """Returns a list of plugins available for a given category

    This is a wrapper around the functions :cpp:func:`lammps_plugin_count()`
    and :cpp:func:`lammps_plugin_name()` of the library interface.

    .. versionadded:: 10Mar2021

    :return: list of style/name pairs of loaded plugins
    :rtype:  list
    """

    available_plugins = []
    num = self.lib.lammps_plugin_count(self.lmp)
    sty = create_string_buffer(100)
    nam = create_string_buffer(100)
    for idx in range(num):
      self.lib.lammps_plugin_name(idx, sty, nam, 100)
      available_plugins.append([sty.value.decode(), nam.value.decode()])
    return available_plugins

  # -------------------------------------------------------------------------

  def set_fix_external_callback(self, fix_name, callback, caller=None):
    import numpy as np

    def callback_wrapper(caller, ntimestep, nlocal, tag_ptr, x_ptr, fext_ptr):
      tag = self.numpy.iarray(self.c_tagint, tag_ptr, nlocal, 1)
      x   = self.numpy.darray(x_ptr, nlocal, 3)
      f   = self.numpy.darray(fext_ptr, nlocal, 3)
      callback(caller, ntimestep, nlocal, tag, x, f)

    cFunc   = self.FIX_EXTERNAL_CALLBACK_FUNC(callback_wrapper)
    cCaller = caller

    self.callback[fix_name] = { 'function': cFunc, 'caller': caller }
    with ExceptionCheck(self):
      self.lib.lammps_set_fix_external_callback(self.lmp, fix_name.encode(), cFunc, cCaller)


  # -------------------------------------------------------------------------

  def get_neighlist(self, idx):
    """Returns an instance of :class:`NeighList` which wraps access to the neighbor list with the given index

    See :py:meth:`lammps.numpy.get_neighlist() <lammps.numpy_wrapper.numpy_wrapper.get_neighlist()>` if you want to use
    NumPy arrays instead of ``c_int`` pointers.

    :param idx: index of neighbor list
    :type  idx: int
    :return: an instance of :class:`NeighList` wrapping access to neighbor list data
    :rtype:  NeighList
    """
    if idx < 0:
        return None
    return NeighList(self, idx)

  # -------------------------------------------------------------------------

  def get_neighlist_size(self, idx):
    """Return the number of elements in neighbor list with the given index

    :param idx: neighbor list index
    :type  idx: int
    :return: number of elements in neighbor list with index idx
    :rtype:  int
     """
    return self.lib.lammps_neighlist_num_elements(self.lmp, idx)

  # -------------------------------------------------------------------------

  def get_neighlist_element_neighbors(self, idx, element):
    """Return data of neighbor list entry

    :param element: neighbor list index
    :type  element: int
    :param element: neighbor list element index
    :type  element: int
    :return: tuple with atom local index, number of neighbors and array of neighbor local atom indices
    :rtype:  (int, int, POINTER(c_int))
    """
    c_iatom = c_int()
    c_numneigh = c_int()
    c_neighbors = POINTER(c_int)()
    self.lib.lammps_neighlist_element_neighbors(self.lmp, idx, element, byref(c_iatom), byref(c_numneigh), byref(c_neighbors))
    return c_iatom.value, c_numneigh.value, c_neighbors

  # -------------------------------------------------------------------------

  def find_pair_neighlist(self, style, exact=True, nsub=0, request=0):
    """Find neighbor list index of pair style neighbor list

    Try finding pair instance that matches style. If exact is set, the pair must
    match style exactly. If exact is 0, style must only be contained. If pair is
    of style pair/hybrid, style is instead matched the nsub-th hybrid sub-style.

    Once the pair instance has been identified, multiple neighbor list requests
    may be found. Every neighbor list is uniquely identified by its request
    index. Thus, providing this request index ensures that the correct neighbor
    list index is returned.

    :param style: name of pair style that should be searched for
    :type  style: string
    :param exact: controls whether style should match exactly or only must be contained in pair style name, defaults to True
    :type  exact: bool, optional
    :param nsub:  match nsub-th hybrid sub-style, defaults to 0
    :type  nsub:  int, optional
    :param request:   index of neighbor list request, in case there are more than one, defaults to 0
    :type  request:   int, optional
    :return: neighbor list index if found, otherwise -1
    :rtype:  int
     """
    style = style.encode()
    exact = int(exact)
    idx = self.lib.lammps_find_pair_neighlist(self.lmp, style, exact, nsub, request)
    return idx

  # -------------------------------------------------------------------------

  def find_fix_neighlist(self, fixid, request=0):
    """Find neighbor list index of fix neighbor list

    :param fixid: name of fix
    :type  fixid: string
    :param request:   index of neighbor list request, in case there are more than one, defaults to 0
    :type  request:   int, optional
    :return: neighbor list index if found, otherwise -1
    :rtype:  int
     """
    fixid = fixid.encode()
    idx = self.lib.lammps_find_fix_neighlist(self.lmp, fixid, request)
    return idx

  # -------------------------------------------------------------------------

  def find_compute_neighlist(self, computeid, request=0):
    """Find neighbor list index of compute neighbor list

    :param computeid: name of compute
    :type  computeid: string
    :param request:   index of neighbor list request, in case there are more than one, defaults to 0
    :type  request:   int, optional
    :return: neighbor list index if found, otherwise -1
    :rtype:  int
     """
    computeid = computeid.encode()
    idx = self.lib.lammps_find_compute_neighlist(self.lmp, computeid, request)
    return idx
