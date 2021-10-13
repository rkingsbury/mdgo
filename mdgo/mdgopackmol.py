# coding: utf-8
# Copyright (c) Tingzheng Hou.
# Distributed under the terms of the MIT License.

"""
This module implements a core class PackmolWrapper for packing molecules
into a single box.

You need the Packmol package to run the code, see
http://m3g.iqm.unicamp.br/packmol or
http://leandro.iqm.unicamp.br/m3g/packmol/home.shtml
for download and setup instructions. You may need to manually
set the folder of the packmol executable to the PATH environment variable.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union

from pymatgen.core import Molecule

from mdgo.volume import molecular_volume

__author__ = "Tingzheng Hou, Ryan Kingsbury"
__version__ = "1.0"
__maintainer__ = "Tingzheng Hou"
__email__ = "tingzheng_hou@berkeley.edu"
__date__ = "Feb - Oct, 2021"


class PackmolWrapper:
    """
    Wrapper for the Packmol software that can be used to pack various types of
    molecules into a one single unit.

    Examples:

        >>> molecules = [{"name": "EMC",
                    "number": 2,
                  "coords": "/Users/th/Downloads/test_selenium/EMC.lmp.xyz"}]
        >>> pw = PackmolWrapper("/path/to/work/dir",
        ...                     molecules,
        ...                     [0., 0., 0., 10., 10., 10.]
        ... )
        >>> pw.make_packmol_input()
        >>> pw.run_packmol()
    """

    def __init__(
        self,
        path: str,
        molecules: List[Dict],
        box: Optional[List[float]] = None,
        tolerance: float = 2.0,
        seed: int = 1,
        control_params: Optional[Dict] = None,
        inputfile: Union[str, Path] = "packmol.inp",
        outputfile: Union[str, Path] = "packmol_out.xyz",
    ):
        """
        Args:
            path: The path to the directory for file i/o. Note that the path
                cannot contain any spaces.
            molecules: A list of dict containing information about molecules to pack
                into the box. Each dict requires three keys:
                    1. "name" - the structure name
                    2. "number" - the number of that molecule to pack into the box
                    3. "coords" - Coordinates in the form of either a Molecule object or
                        a path to a file.
                Example:
                    {"name": "water",
                     "number": 500,
                     "coords": "/path/to/input/file.xyz"}
            box: A list of box dimensions xlo, ylo, zlo, xhi, yhi, zhi, in Å. If set to None
                (default), mdgo will estimate the required box size based on the volumes of
                the provided molecules using mdgo.volume.molecular_volume()
            tolerance: Tolerance for packmol, in Å.
            seed: Random seed for packmol. Use a value of 1 (default) for deterministic
                output, or -1 to generate a new random seed from the current time.
            inputfile: Path to the input file. Default to 'packmol.inp'.
            outputfile: Path to the output file. Default to 'output.xyz'.
        """
        self.path = path
        self.input = os.path.join(self.path, inputfile)
        self.output = os.path.join(self.path, outputfile)
        self.screen = os.path.join(self.path, "packmol.stdout")
        self.molecules = molecules
        self.control_params = control_params if control_params else {}
        self.box = box
        self.tolerance = tolerance
        self.seed = seed

    def run_packmol(self, timeout=30):
        """Run packmol and write out the packed structure.
        Args:
            timeout: Timeout in seconds.
        Raises:
            ValueError if packmol does not succeed in packing the box.
            TimeoutExpiredError if packmold does not finish within the timeout.
        """
        try:
            p = subprocess.run(
                "packmol < '{}'".format(self.input),
                check=True,
                shell=True,
                timeout=timeout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # this workaround is needed because packmol can fail to find
            # a solution but still return a zero exit code
            # see https://github.com/m3g/packmol/issues/28
            # all_stdout = str(p.stdout)
            # for line in p.stdout.decode():
            if "ERROR" in p.stdout.decode():
                msg = p.stdout.decode().split("ERROR")[-1]
                raise ValueError(f"Packmol failed with return code 0 and stdout: {msg}")
        except subprocess.CalledProcessError as e:
            raise ValueError("Packmol failed with errorcode {} and stderr: {}".format(e.returncode, e.stderr)) from e
        else:
            with open(self.screen, "w") as out:
                out.write(p.stdout.decode())

    def make_packmol_input(self):
        """Make a Packmol usable input file."""

        if self.box:
            box_list = " ".join(str(i) for i in self.box)
        else:
            # estimate the total volume of all molecules
            net_volume = 0.0
            for idx, d in enumerate(self.molecules):
                if not isinstance(d["coords"], Molecule):
                    mol = Molecule.from_file(d["coords"])
                else:
                    mol = d["coords"]
                # molecular volume in cubic Å
                vol = molecular_volume(mol, radii_type="pymatgen", molar_volume=False)
                # pad the calculated length by an amount related to the tolerance parameter
                # the amount to add was determined arbitrarily
                vol *= self.tolerance
                net_volume += vol * d["number"]

            box_length = net_volume ** (1.0 / 3.0)
            print(f"Auto determined box size is {box_length:.1f} Å per side.")
            box_list = "0.0 0.0 0.0 {:.1f} {:.1f} {:.1f}".format(box_length, box_length, box_length)

        with open(self.input, "w") as out:
            out.write("# " + " + ".join(str(d["number"]) + " " + d["name"] for d in self.molecules) + "\n")
            out.write("# Packmol input generated by mdgo.\n")
            for k, v in self.control_params.items():
                if isinstance(v, list):
                    out.write("{} {}\n".format(k, " ".join(str(x) for x in v)))
                else:
                    out.write("{} {}\n".format(k, str(v)))
            out.write("seed {}\n".format(self.seed))
            out.write("tolerance {}\n\n".format(self.tolerance))

            out.write("filetype xyz\n\n")
            # NOTE - output filename MUST be enclosed in double quotes in order to work
            # when there are spaces in the filename. Single quotes will not work.
            out.write(f'output "{self.output}"\n\n')

            for i, d in enumerate(self.molecules):
                if isinstance(d["coords"], str):
                    out.write("structure {}\n".format(d["coords"]))
                elif isinstance(d["coords"], Path):
                    out.write("structure {}\n".format(str(d["coords"])))
                elif isinstance(d["coords"], Molecule):
                    d["coords"].to(filename=f"packmol_molecule_{i}.xyz")
                    out.write("structure {}\n".format(f"packmol_molecule_{i}.xyz"))
                out.write("  number {}\n".format(str(d["number"])))
                out.write("  inside box {}\n".format(box_list))
                out.write("end structure\n\n")


if __name__ == "__main__":
    """
    molecules = [{"name": "EMC",
                  "number": 2,
                  "coords": "/Users/th/Downloads/test_selenium/EMC.lmp.xyz"}]
    pw = PackmolWrapper("/Users/th/Downloads/test_selenium/", molecules,
                        [0., 0., 0., 10., 10., 10.])
    pw.make_packmol_input()
    pw.run_packmol()
    """
