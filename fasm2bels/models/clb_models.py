from .verilog_modeling import Bel, Site


def get_clb_site(db, grid, tile, site):
    """ Return the prjxray.tile.Site object for the given CLB site. """
    gridinfo = grid.gridinfo_at_tilename(tile)
    tile_type = db.get_tile_type(gridinfo.tile_type)

    sites = sorted(tile_type.get_instance_sites(gridinfo), key=lambda x: x.x)

    return sites[int(site[-1])]


def get_lut_init(site, lut):
    """ Return the INIT value for the specified LUT. """
    init = site.decode_multi_bit_feature('{}LUT.INIT'.format(lut))
    return "64'b{:064b}".format(init)


def get_shifted_lut_init(site, lut, shift=0):
    """ Return the shifted INIT value as integer. The init input is a string."""
    init = get_lut_init(site, lut)
    int_init = int(init.split('b')[-1], 2)

    return int_init << shift


def create_lut(site, lut):
    """ Create the BEL for the specified LUT. """
    bel = Bel('LUT6_2', lut + 'LUT', priority=3)
    bel.set_bel(lut + '6LUT')

    for idx in range(6):
        site.add_sink(bel, 'I{}'.format(idx), '{}{}'.format(lut, idx + 1))

    site.add_internal_source(bel, 'O6', lut + 'O6')
    site.add_internal_source(bel, 'O5', lut + 'O5')

    return bel


def get_srl32_init(site, srl):

    lut_init = get_lut_init(site, srl)
    bits = lut_init.replace("64'b", "")

    assert bits[1::2] == bits[::2]

    return "32'b{}".format(bits[::2])


def create_srl32(site, srl):
    bel = Bel('SRLC32E', srl + 'SRL', priority=2)
    bel.set_bel(srl + '6LUT')

    site.add_sink(bel, 'CLK', 'CLK')
    site.add_sink(bel, 'D', '{}I'.format(srl))

    for idx in range(5):
        site.add_sink(bel, 'A[{}]'.format(idx), '{}{}'.format(srl, idx + 2))

    site.add_internal_source(bel, 'Q', srl + 'O6')

    return bel


def get_srl16_init(site, srl):
    """
    Decodes SRL16 INIT parameter. Returns two initialization strings, each one
    for one of two SRL16s.
    """

    lut_init = get_lut_init(site, srl)
    bits = lut_init.replace("64'b", "")

    assert bits[1::2] == bits[::2]

    srl_init = bits[::2]
    return "16'b{}".format(srl_init[:16]), "16'b{}".format(srl_init[16:])


def create_srl16(site, srl, srl_type, part):
    """
    Create an instance of SRL16 bel. Either for "x6LUT" or for "x5LUT"
    depending on the part parameter.
    """

    assert part == '5' or part == '6'

    bel = Bel(srl_type, srl + part + 'SRL', priority=2)
    bel.set_bel(srl + part + 'LUT')

    site.add_sink(bel, 'CLK', 'CLK')

    if part == '5':
        site.add_sink(bel, 'D', '{}I'.format(srl))
    if part == '6':
        site.add_sink(bel, 'D', '{}X'.format(srl))

    for idx in range(4):
        site.add_sink(bel, 'A{}'.format(idx), '{}{}'.format(srl, idx + 2))

    site.add_internal_source(bel, 'Q', srl + 'O' + part)

    return bel


def decode_dram(site):
    """ Decode the modes of each LUT in the slice based on set features.

    Returns dictionary of lut position (e.g. 'A') to lut mode.
    """
    lut_ram = {}
    lut_small = {}
    for lut in 'ABCD':
        lut_ram[lut] = site.has_feature('{}LUT.RAM'.format(lut))
        lut_small[lut] = site.has_feature('{}LUT.SMALL'.format(lut))

    di = {}
    for lut in 'ABC':
        di[lut] = site.has_feature('{}LUT.DI1MUX.{}I'.format(lut, lut))

    lut_modes = {}
    if site.has_feature('WA8USED'):
        assert site.has_feature('WA7USED')
        assert lut_ram['A']
        assert lut_ram['B']
        assert lut_ram['C']
        assert lut_ram['D']

        lut_modes['A'] = 'RAM256X1S'
        lut_modes['B'] = 'RAM256X1S'
        lut_modes['C'] = 'RAM256X1S'
        lut_modes['D'] = 'RAM256X1S'
        return lut_modes

    if site.has_feature('WA7USED'):
        if not lut_ram['A']:
            assert not lut_ram['B']
            assert lut_ram['C']
            assert lut_ram['D']
            lut_modes['A'] = 'LUT'
            lut_modes['B'] = 'LUT'
            lut_modes['C'] = 'RAM128X1S'
            lut_modes['D'] = 'RAM128X1S'

            return lut_modes

        assert lut_ram['B']

        if di['B']:
            lut_modes['A'] = 'RAM128X1S'
            lut_modes['B'] = 'RAM128X1S'
            lut_modes['C'] = 'RAM128X1S'
            lut_modes['D'] = 'RAM128X1S'
        else:
            assert lut_ram['B']
            assert lut_ram['C']
            assert lut_ram['D']

            lut_modes['A'] = 'RAM128X1D'
            lut_modes['B'] = 'RAM128X1D'
            lut_modes['C'] = 'RAM128X1D'
            lut_modes['D'] = 'RAM128X1D'

        return lut_modes

    all_ram = all(lut_ram[lut] for lut in 'ABCD')
    all_small = all(lut_small[lut] for lut in 'ABCD')

    if all_ram and not all_small:
        return {'D': 'RAM64M'}
    elif all_ram and all_small:
        return {'D': 'RAM32M'}
    else:
        # Remaining modes:
        # RAM32X1S, RAM32X1D, RAM64X1S, RAM64X1D
        remaining = set('ABCD')

        for lut in 'AC':
            if lut_ram[lut] and di[lut]:
                remaining.remove(lut)

                if lut_small[lut]:
                    lut_modes[lut] = 'RAM32X1S'
                else:
                    lut_modes[lut] = 'RAM64X1S'

        for lut in 'BD':
            if not lut_ram[lut]:
                continue

            minus_one = chr(ord(lut) - 1)
            if minus_one in remaining:
                if lut_ram[minus_one]:
                    remaining.remove(lut)
                    remaining.remove(minus_one)
                    if lut_small[lut]:
                        lut_modes[lut] = 'RAM32X1D'
                        lut_modes[minus_one] = 'RAM32X1D'
                    else:
                        lut_modes[lut] = 'RAM64X1D'
                        lut_modes[minus_one] = 'RAM64X1D'

            if lut in remaining:
                remaining.remove(lut)
                if lut_small[lut]:
                    lut_modes[lut] = 'RAM32X1S'
                else:
                    lut_modes[lut] = 'RAM64X1S'

        for lut in remaining:
            lut_modes[lut] = 'LUT'

        return lut_modes


def ff_bel(site, lut, ff5):
    """ Returns FF information for given FF.

    site (Site): Site object
    lut (str): FF in question (e.g. 'A')
    ff5 (bool): True if the 5FF versus the FF.

    Returns tuple of (module name, clock pin, clock enable pin, reset pin,
        init parameter).

    """
    ffsync = site.has_feature('FFSYNC')
    latch = site.has_feature('LATCH') and not ff5
    zrst = site.has_feature('{}{}FF.ZRST'.format(lut, '5' if ff5 else ''))
    zini = site.has_feature('{}{}FF.ZINI'.format(lut, '5' if ff5 else ''))
    init = int(not zini)

    if latch:
        assert not ffsync

    return {
        (False, False, False): ('FDPE', 'C', 'CE', 'PRE', init),
        (True, False, False): ('FDSE', 'C', 'CE', 'S', init),
        (True, False, True): ('FDRE', 'C', 'CE', 'R', init),
        (False, False, True): ('FDCE', 'C', 'CE', 'CLR', init),
        (False, True, True): ('LDCE', 'G', 'GE', 'CLR', init),
        (False, True, False): ('LDPE', 'G', 'GE', 'PRE', init),
    }[(ffsync, latch, zrst)]


def cleanup_carry4(top, site):
    """ Performs post-routing cleanups of CARRY4 bel required for SLICE.

    Cleanups:
     - Detect if CARRY4 is required.  If not, remove from site.
     - Remove connections to CARRY4 that are not in used (e.g. if C[3] and
       CO[3] are not used, disconnect S[3] and DI[2]).
    """

    carry4 = site.maybe_get_bel('CARRY4')
    if carry4 is not None:

        # Simplest check is if the CARRY4 has output in used by either the OUTMUX
        # or the FFMUX, if any of these muxes are enable, CARRY4 must remain.
        co_in_use = [False for _ in range(4)]
        o_in_use = [False for _ in range(4)]
        for idx, lut in enumerate('ABCD'):
            if site.has_feature('{}FFMUX.XOR'.format(lut)):
                o_in_use[idx] = True

            if site.has_feature('{}FFMUX.CY'.format(lut)):
                co_in_use[idx] = True

            if site.has_feature('{}OUTMUX.XOR'.format(lut)):
                o_in_use[idx] = True

            if site.has_feature('{}OUTMUX.CY'.format(lut)):
                co_in_use[idx] = True

        # No outputs in the SLICE use CARRY4, check if the COUT line is in use.
        for sink in top.find_sinks_from_source(site, 'COUT'):
            co_in_use[idx] = True
            break

        for idx in [3, 2, 1, 0]:
            if co_in_use[idx] or o_in_use[idx]:
                for odx in range(idx):
                    co_in_use[odx] = True
                    o_in_use[odx] = True

                break

        if not any(co_in_use) and not any(o_in_use):
            # No outputs in use, remove entire BEL
            top.remove_bel(site, carry4)
        else:
            pass
            """
            for idx in range(4):
                if not o_in_use[idx] and not co_in_use[idx]:
                    sink_wire_pkey = site.remove_internal_sink(
                        carry4, 'S[{}]'.format(idx)
                    )
                    if sink_wire_pkey is not None:
                        top.remove_sink(sink_wire_pkey)

                    sink_wire_pkey = site.remove_internal_sink(
                        carry4, 'DI[{}]'.format(idx)
                    )
                    if sink_wire_pkey is not None:
                        top.remove_sink(sink_wire_pkey)
            """


def cleanup_srl(top, site):
    """Performs post-routing cleanups of SRLs required for SLICE.

    Cleanups:
     - For each LUT if in 2xSRL16 mode detect whether both SRL16 are used.
       removes unused ones.
    """

    # Remove unused SRL16
    for i, row in enumerate("ABCD"):

        # n5SRL, check O5
        srl = site.maybe_get_bel("{}5SRL".format(row))
        if srl is not None:

            if not site.has_feature("{}OUTMUX.O5".format(row)) and \
               not site.has_feature("{}FFMUX.O5".format(row)):
                top.remove_bel(site, srl)

        # n6SRL, check O6 and MC31
        srl = site.maybe_get_bel("{}6SRL".format(row))
        if srl is not None:

            # nOUTMUX, nFFMUX
            noutmux_o6_used = site.has_feature("{}OUTMUX.O6".format(row))
            nffmux_o6_used = site.has_feature("{}FFMUX.O6".format(row))

            # nUSED
            nused_used = True
            sinks = list(top.find_sinks_from_source(site, row))
            if len(sinks) == 0:
                nused_used = False

            # n7MUX
            f7nmux_used = True
            if row in "AB" and site.maybe_get_bel("F7AMUX") is None:
                f7nmux_used = False
            if row in "CD" and site.maybe_get_bel("F7BMUX") is None:
                f7nmux_used = False

            # A6SRL MC31 output
            if row == "A":
                mc31_used = site.has_feature("DOUTMUX.MC31") or \
                    site.has_feature("DFFMUX.MC31")
            else:
                mc31_used = False

            # Remove if necessary
            anything_used = nused_used or noutmux_o6_used or nffmux_o6_used or\
                f7nmux_used or mc31_used

            if not anything_used:
                top.remove_bel(site, srl)


def cleanup_dram(top, site):
    """Performs post-routing cleanup of DRAMs for SLICEMs.

    Depending on the DRAM mode, the fake sinks are masked so that they
    are not present in the verilog output.
    """
    lut_modes = decode_dram(site)

    if 'RAM128X1D' in lut_modes.values():
        ram128 = site.maybe_get_bel('RAM128X1D')
        for idx in range(6):
            site.mask_sink(ram128, 'ADDR_C[{}]'.format(idx))
            site.mask_sink(ram128, 'DATA_A[{}]'.format(idx))

    if 'RAM128X1S' in lut_modes.values():
        if lut_modes['D'] == 'RAM128X1S' and lut_modes['C'] == 'RAM128X1S':
            ram128 = site.maybe_get_bel('RAM128X1S_CD')
            for idx in range(6):
                site.mask_sink(ram128, 'ADDR_C{}'.format(idx))

        if 'B' in lut_modes.keys():
            if lut_modes['B'] == 'RAM128X1S' and lut_modes['A'] == 'RAM128X1S':
                ram128 = site.maybe_get_bel('RAM128X1S_AB')
                for idx in range(6):
                    site.mask_sink(ram128, 'ADDR_A{}'.format(idx))

    if 'RAM256X1S' in lut_modes.values():
        ram256 = site.maybe_get_bel('RAM256X1S')

        site.mask_sink(ram256, 'AX')
        for idx in range(6):
            site.mask_sink(ram256, 'ADDR_C[{}]'.format(idx))
            site.mask_sink(ram256, 'ADDR_B[{}]'.format(idx))
            site.mask_sink(ram256, 'ADDR_A[{}]'.format(idx))


def cleanup_slice(top, site):
    """Performs post-routing cleanups required for SLICE."""

    # Cleanup CARRY4 stuff
    cleanup_carry4(top, site)

    # Cleanup SRL stuff
    cleanup_srl(top, site)

    # Cleanup DRAM stuff
    cleanup_dram(top, site)


def munge_ram32m_init(init):
    """ RAM32M INIT is interleaved, while the underlying data is not.

    INIT[::2] = INIT[:32]
    INIT[1::2] = INIT[32:]

    """

    bits = init.replace("64'b", "")[::-1]
    assert len(bits) == 64

    out_init = ['0' for _ in range(64)]
    out_init[::2] = bits[:32]
    out_init[1::2] = bits[32:]

    return "64'b{}".format(''.join(out_init[::-1]))


def di_mux(site, bel, di_port, lut):
    """ Implements DI1 mux. """
    if lut == 'A':
        if site.has_feature('ALUT.DI1MUX.AI'):
            site.add_sink(bel, di_port, "AI")
        else:
            if site.has_feature('BLUT.DI1MUX.BI'):
                site.add_sink(bel, di_port, "BI")
            else:
                site.add_sink(bel, di_port, "DI")
    elif lut == 'B':
        if site.has_feature('BLUT.DI1MUX.BI'):
            site.add_sink(bel, di_port, "BI")
        else:
            site.add_sink(bel, di_port, "DI")
    elif lut == 'C':
        if site.has_feature('CLUT.DI1MUX.CI'):
            site.add_sink(bel, di_port, "CI")
        else:
            site.add_sink(bel, di_port, "DI")
    elif lut == 'D':
        site.add_sink(bel, di_port, "DI")
    else:
        assert False, lut


def process_slice(top, s):
    """ Convert SLICE features in Bel and Site objects.

    """
    """
    Available options:

    LUT/DRAM/SRL:
    SLICE[LM]_X[01].[ABCD]LUT.INIT[63:0]
    SLICEM_X0.[ABCD]LUT.RAM
    SLICEM_X0.[ABCD]LUT.SMALL
    SLICEM_X0.[ABCD]LUT.SRL

    FF:
    SLICE[LM]_X[01].[ABCD]5?FF.ZINI
    SLICE[LM]_X[01].[ABCD]5?FF.ZRST
    SLICE[LM]_X[01].CLKINV
    SLICE[LM]_X[01].FFSYNC
    SLICE[LM]_X[01].LATCH
    SLICE[LM]_X[01].CEUSEDMUX
    SLICE[LM]_X[01].SRUSEDMUX

    CARRY4:
    SLICE[LM]_X[01].PRECYINIT = AX|CIN|C0|C1

    Muxes:
    SLICE[LM]_X[01].CARRY4.ACY0
    SLICE[LM]_X[01].CARRY4.BCY0
    SLICE[LM]_X[01].CARRY4.CCY0
    SLICE[LM]_X[01].CARRY4.DCY0
    SLICE[LM]_X[01].[ABCD]5FFMUX.IN_[AB]
    SLICE[LM]_X[01].[ABCD]AFFMUX = [ABCD]X|CY|XOR|F[78]|O5|O6
    SLICE[LM]_X[01].[ABCD]OUTMUX = CY|XOR|F[78]|O5|O6|[ABCD]5Q
    SLICEM_X0.WA7USED
    SLICEM_X0.WA8USED
    SLICEM_X0.WEMUX.CE
    """

    aparts = s[0].feature.split('.')
    site = Site(s,
                get_clb_site(top.db, top.grid, tile=aparts[0], site=aparts[1]))

    mlut = aparts[1].startswith('SLICEM')

    def connect_ce_sr(bel, ce, sr):
        if site.has_feature('CEUSEDMUX'):
            site.add_sink(bel, ce, 'CE')
        else:
            bel.connections[ce] = 1

        if site.has_feature('SRUSEDMUX'):
            site.add_sink(bel, sr, 'SR')
        else:
            bel.connections[sr] = 0

    IS_C_INVERTED = int(site.has_feature('CLKINV'))

    if mlut:
        if site.has_feature('WEMUX.CE'):
            WE = 'CE'
        else:
            WE = 'WE'

    if site.has_feature('DLUT.RAM'):
        # Must be a SLICEM to have RAM set.
        assert mlut
    else:
        for row in 'ABC':
            assert not site.has_feature('{}LUT.RAM'.format(row))

    muxes = set(('F7AMUX', 'F7BMUX', 'F8MUX'))

    luts = {}
    srls = {}

    # Add BELs for LUTs/RAMs
    if not site.has_feature('DLUT.RAM'):
        for row in 'ABCD':

            # SRL
            if site.has_feature('{}LUT.SRL'.format(row)):

                # Cannot have both SRL and DRAM
                assert not site.has_feature('{}LUT.RAM'.format(row))

                # SRL32
                if not site.has_feature('{}LUT.SMALL'.format(row)):
                    srl = create_srl32(site, row)
                    srl.parameters['INIT'] = get_srl32_init(site, row)

                    site.add_sink(srl, 'CE', WE)

                    if row == 'A' and site.has_feature('DOUTMUX.MC31'):
                        site.add_internal_source(srl, 'Q31', 'AMC31')
                    if row == 'A' and site.has_feature('DFFMUX.MC31'):
                        site.add_internal_source(srl, 'Q31', 'AMC31')

                    site.add_bel(srl)
                    srls[row] = (srl, )

                # 2x SRL16
                else:

                    srls[row] = []
                    init = get_srl16_init(site, row)

                    for i, part in enumerate(['5', '6']):

                        # Determine whether to use SRL16E or SRLC16E
                        srl_type = 'SRL16E'
                        use_mc31 = False

                        if part == '6':

                            if row == 'A' and site.has_feature('DOUTMUX.MC31'):
                                srl_type = 'SRLC16E'
                                use_mc31 = True
                            if row == 'A' and site.has_feature('DFFMUX.MC31'):
                                srl_type = 'SRLC16E'
                                use_mc31 = True

                            if row == 'D' and site.has_feature(
                                    'CLUT.DI1MUX.DI_DMC31'):
                                srl_type = 'SRLC16E'
                            if row == 'C' and site.has_feature(
                                    'BLUT.DI1MUX.DI_CMC31'):
                                srl_type = 'SRLC16E'
                            if row == 'B' and site.has_feature(
                                    'ALUT.DI1MUX.DI_BMC31'):
                                srl_type = 'SRLC16E'

                        # Create the SRL
                        srl = create_srl16(site, row, srl_type, part)
                        srl.parameters['INIT'] = init[i]

                        site.add_sink(srl, 'CE', WE)

                        if use_mc31 and srl_type == 'SRLC16E':
                            site.add_internal_source(srl, 'Q15', 'AMC31')

                        site.add_bel(srl, name="{}{}SRL".format(row, part))
                        srls[row].append(srl)

                    srls[row] = tuple(srls[row])

            # LUT
            else:
                luts[row] = create_lut(site, row)
                luts[row].parameters['INIT'] = get_lut_init(site, row)
                site.add_bel(luts[row])
    else:
        # DRAM is active.  Determine what BELs are in use.
        lut_modes = decode_dram(site)

        if lut_modes['D'] == 'RAM256X1S':
            ram256 = Bel('RAM256X1S', priority=3)
            site.add_sink(ram256, 'WE', WE)
            site.add_sink(ram256, 'WCLK', 'CLK')
            site.add_sink(ram256, 'D', 'DI')

            for idx in range(6):
                site.add_sink(ram256, 'A[{}]'.format(idx),
                              "D{}".format(idx + 1))
                # Add fake sinks as they need to be routed to
                site.add_sink(ram256, 'ADDR_C[{}]'.format(idx),
                              "C{}".format(idx + 1))
                site.add_sink(ram256, 'ADDR_B[{}]'.format(idx),
                              "B{}".format(idx + 1))
                site.add_sink(ram256, 'ADDR_A[{}]'.format(idx),
                              "A{}".format(idx + 1))

            site.add_sink(ram256, 'A[6]', "CX")
            site.add_sink(ram256, 'A[7]', "BX")
            site.add_internal_source(ram256, 'O', 'F8MUX_O')

            # Add fake sink to preserve routing thorugh AX pin.
            # The AX pin is used in the same net as for the CX pin.
            site.add_sink(ram256, 'AX', "AX")

            ram256.parameters['INIT'] = (
                get_shifted_lut_init(site, 'D')
                | get_shifted_lut_init(site, 'C', 64)
                | get_shifted_lut_init(site, 'B', 128)
                | get_shifted_lut_init(site, 'A', 192))

            site.add_bel(ram256, name="RAM256X1S")

            muxes = set()

            del lut_modes['A']
            del lut_modes['B']
            del lut_modes['C']
            del lut_modes['D']
        elif lut_modes['D'] == 'RAM128X1S':
            ram128 = Bel('RAM128X1S', name='RAM128X1S_CD', priority=3)
            site.add_sink(ram128, 'WE', WE)
            site.add_sink(ram128, 'WCLK', "CLK")
            site.add_sink(ram128, 'D', "DI")

            for idx in range(6):
                site.add_sink(ram128, 'A{}'.format(idx), "D{}".format(idx + 1))
                # Add fake sink to route through the C[N] pins
                site.add_sink(ram128, 'ADDR_C{}'.format(idx),
                              "C{}".format(idx + 1))

            site.add_sink(ram128, 'A6', "CX")
            site.add_internal_source(ram128, 'O', 'F7BMUX_O')

            ram128.parameters['INIT'] = (get_shifted_lut_init(site, 'D')
                                         | get_shifted_lut_init(site, 'C', 64))

            site.add_bel(ram128, name='RAM128X1S_CD')
            muxes.remove('F7BMUX')

            del lut_modes['C']
            del lut_modes['D']

            if lut_modes['B'] == 'RAM128X1S':
                ram128 = Bel('RAM128X1S', name='RAM128X1S_AB', priority=4)
                site.add_sink(ram128, 'WE', WE)
                site.add_sink(ram128, 'WCLK', "CLK")
                site.add_sink(ram128, 'D', "BI")

                for idx in range(6):
                    site.add_sink(ram128, 'A{}'.format(idx),
                                  "B{}".format(idx + 1))
                    # Add fake sink to route through the A[N] pins
                    site.add_sink(ram128, 'ADDR_A{}'.format(idx),
                                  "A{}".format(idx + 1))

                site.add_sink(ram128, 'A6', "AX")

                site.add_internal_source(ram128, 'O', 'F7AMUX_O')

                ram128.parameters['INIT'] = (get_shifted_lut_init(site, 'B')
                                             | get_shifted_lut_init(
                                                 site, 'A', 64))

                site.add_bel(ram128, name='RAM128X1S_AB')

                muxes.remove('F7AMUX')

                del lut_modes['A']
                del lut_modes['B']

        elif lut_modes['D'] == 'RAM128X1D':
            ram128 = Bel('RAM128X1D', priority=3)

            site.add_sink(ram128, 'WE', WE)
            site.add_sink(ram128, 'WCLK', "CLK")
            site.add_sink(ram128, 'D', "DI")

            for idx in range(6):
                site.add_sink(ram128, 'A[{}]'.format(idx),
                              "D{}".format(idx + 1))
                # Add fake sink to route through the C[N] pins
                site.add_sink(ram128, 'ADDR_C[{}]'.format(idx),
                              "C{}".format(idx + 1))
                site.add_sink(ram128, 'DPRA[{}]'.format(idx),
                              "B{}".format(idx + 1))
                # Add fake sink to route through the A[N] pins
                site.add_sink(ram128, 'DATA_A[{}]'.format(idx),
                              "A{}".format(idx + 1))

            site.add_sink(ram128, 'A[6]', "CX")
            site.add_sink(ram128, 'DPRA[6]', "AX")

            site.add_internal_source(ram128, 'SPO', 'F7BMUX_O')
            site.add_internal_source(ram128, 'DPO', 'F7AMUX_O')

            ram128.parameters['INIT'] = (get_shifted_lut_init(site, 'D')
                                         | get_shifted_lut_init(site, 'C', 64))

            other_init = (get_shifted_lut_init(site, 'B')
                          | get_shifted_lut_init(site, 'A', 64))

            assert ram128.parameters['INIT'] == other_init

            site.add_bel(ram128, name="RAM128X1D")

            muxes.remove('F7AMUX')
            muxes.remove('F7BMUX')

            del lut_modes['A']
            del lut_modes['B']
            del lut_modes['C']
            del lut_modes['D']
        elif lut_modes['D'] == 'RAM64M':
            del lut_modes['D']

            ram64m = Bel('RAM64M', name='RAM64M', priority=3)

            site.add_sink(ram64m, 'WE', WE)
            site.add_sink(ram64m, 'WCLK', "CLK")

            di_mux(site, ram64m, 'DIA', 'A')
            di_mux(site, ram64m, 'DIB', 'B')
            di_mux(site, ram64m, 'DIC', 'C')
            di_mux(site, ram64m, 'DID', 'D')

            for lut in 'ABCD':
                for idx in range(6):
                    site.add_sink(ram64m, 'ADDR{}[{}]'.format(lut, idx),
                                  "{}{}".format(lut, idx + 1))

                site.add_internal_source(ram64m, 'DO' + lut, lut + "O6")

                ram64m.parameters['INIT_' + lut] = get_lut_init(site, lut)

            site.add_bel(ram64m)
        elif lut_modes['D'] == 'RAM32M':
            del lut_modes['D']

            ram32m = Bel('RAM32M', name='RAM32M', priority=3)

            site.add_sink(ram32m, 'WE', WE)
            site.add_sink(ram32m, 'WCLK', "CLK")

            di_mux(site, ram32m, 'DIA[0]', 'A')
            di_mux(site, ram32m, 'DIB[0]', 'B')
            di_mux(site, ram32m, 'DIC[0]', 'C')
            di_mux(site, ram32m, 'DID[0]', 'D')

            for lut in 'ABCD':
                site.add_sink(ram32m, 'DI{}[1]'.format(lut), lut + "X")
                site.add_internal_source(ram32m, 'DO{}[1]'.format(lut),
                                         lut + "O6")

                site.add_internal_source(ram32m, 'DO{}[0]'.format(lut),
                                         lut + "O5")

                for idx in range(5):
                    site.add_sink(ram32m, 'ADDR{}[{}]'.format(lut, idx),
                                  "{}{}".format(lut, idx + 1))

                ram32m.parameters['INIT_' + lut] = munge_ram32m_init(
                    get_lut_init(site, lut))

            site.add_bel(ram32m)

        for priority, lut in zip([4, 3], 'BD'):
            if lut not in lut_modes:
                continue

            minus_one = chr(ord(lut) - 1)

            if lut_modes[lut] == 'RAM64X1D':
                assert lut_modes[minus_one] == lut_modes[lut]

                ram64 = Bel(
                    'RAM64X1D',
                    name='RAM64X1D_' + minus_one + lut,
                    priority=priority)
                ram64.set_bel(minus_one + '6LUT')

                site.add_sink(ram64, 'WE', WE)
                site.add_sink(ram64, 'WCLK', "CLK")
                di_mux(site, ram64, 'D', lut)

                for idx in range(6):
                    site.add_sink(ram64, 'A{}'.format(idx), "{}{}".format(
                        lut, idx + 1))
                    site.add_sink(ram64, 'DPRA{}'.format(idx), "{}{}".format(
                        minus_one, idx + 1))

                site.add_internal_source(ram64, 'SPO', lut + "O6")
                site.add_internal_source(ram64, 'DPO', minus_one + "O6")

                ram64.parameters['INIT'] = get_lut_init(site, lut)
                other_init = get_lut_init(site, minus_one)

                assert ram64.parameters['INIT'] == other_init

                site.add_bel(ram64)

                del lut_modes[lut]
                del lut_modes[minus_one]
            elif lut_modes[lut] == 'RAM32X1D':
                ram32 = [
                    Bel('RAM32X1D',
                        name='RAM32X1D_{}_{}'.format(lut, idx),
                        priority=priority) for idx in range(2)
                ]

                for idx in range(2):
                    site.add_sink(ram32[idx], 'WE', WE)
                    site.add_sink(ram32[idx], 'WCLK', "CLK")
                    for aidx in range(5):
                        site.add_sink(ram32[idx], 'A{}'.format(aidx),
                                      "{}{}".format(lut, aidx + 1))
                        site.add_sink(ram32[idx], 'DPRA{}'.format(aidx),
                                      "{}{}".format(minus_one, aidx + 1))

                site.add_sink(ram32[0], 'D', lut + "X")
                site.add_internal_source(ram32[0], 'SPO', lut + "O6")
                site.add_internal_source(ram32[0], 'DPO', minus_one + "O6")
                ram32[0].set_bel('{}6LUT'.format(lut))

                di_mux(site, ram32[1], 'D', lut)
                site.add_internal_source(ram32[1], 'SPO', lut + "O5")
                site.add_internal_source(ram32[1], 'DPO', minus_one + "O5")
                ram32[1].set_bel('{}5LUT'.format(lut))

                lut_init = get_lut_init(site, lut)
                other_init = get_lut_init(site, minus_one)
                assert lut_init == other_init

                bits = lut_init.replace("64'b", "")
                assert len(bits) == 64
                ram32[0].parameters['INIT'] = "32'b{}".format(bits[:32])
                ram32[1].parameters['INIT'] = "32'b{}".format(bits[32:])

                site.add_bel(ram32[0])
                site.add_bel(ram32[1])

                del lut_modes[lut]
                del lut_modes[minus_one]

        for priority, lut in zip([6, 5, 4, 3], 'ABCD'):
            if lut not in lut_modes:
                continue

            if lut_modes[lut] == 'LUT':
                luts[lut] = create_lut(site, lut)
                luts[lut].parameters['INIT'] = get_lut_init(site, lut)
                site.add_bel(luts[lut])
            elif lut_modes[lut] == 'RAM64X1S':
                ram64 = Bel(
                    'RAM64X1S', name='RAM64X1S_' + lut, priority=priority)

                site.add_sink(ram64, 'WE', WE)
                site.add_sink(ram64, 'WCLK', "CLK")
                di_mux(site, ram64, 'D', lut)

                for idx in range(6):
                    site.add_sink(ram64, 'A{}'.format(idx), "{}{}".format(
                        lut, idx + 1))

                site.add_internal_source(ram64, 'O', lut + "O6")

                ram64.parameters['INIT'] = get_lut_init(site, lut)

                site.add_bel(ram64)
            elif lut_modes[lut] == 'RAM32X1S':
                ram32 = [
                    Bel('RAM32X1S',
                        name='RAM32X1S_{}_{}'.format(lut, idx),
                        priority=priority) for idx in range(2)
                ]

                for idx in range(2):
                    site.add_sink(ram32[idx], 'WE', WE)
                    site.add_sink(ram32[idx], 'WCLK', "CLK")
                    for aidx in range(5):
                        site.add_sink(ram32[idx], 'A{}'.format(aidx),
                                      "{}{}".format(lut, aidx + 1))

                site.add_sink(ram32[0], 'D', lut + "X")
                site.add_internal_source(ram32[0], 'O', lut + "O6")
                ram32[0].set_bel('{}6LUT'.format(lut))

                di_mux(site, ram32[1], 'D', lut)
                site.add_internal_source(ram32[1], 'O', lut + "O5")
                ram32[1].set_bel('{}5LUT'.format(lut))

                lut_init = get_lut_init(site, lut)

                bits = lut_init.replace("64'b", "")
                assert len(bits) == 64
                ram32[0].parameters['INIT'] = "32'b{}".format(bits[:32])
                ram32[1].parameters['INIT'] = "32'b{}".format(bits[32:])

                site.add_bel(ram32[0])
                site.add_bel(ram32[1])
            else:
                assert False, lut_modes[lut]

    # Detect SRL chains
    srl_chains = set()

    if "D" in srls and "C" in srls and site.has_feature(
            'CLUT.DI1MUX.DI_DMC31'):
        srl_chains.add("DC")

    if "C" in srls and "B" in srls and site.has_feature(
            'BLUT.DI1MUX.DI_CMC31'):
        srl_chains.add("CB")

    if "B" in srls and "A" in srls and site.has_feature(
            'ALUT.DI1MUX.BDI1_BMC31'):
        srl_chains.add("BA")

    # SRL chain connections
    for chain in srl_chains:
        src = chain[0]
        dst = chain[1]

        if site.has_feature("{}LUT.SMALL".format(src)):
            q = "Q15"
        else:
            q = "Q31"

        site.add_internal_source(srls[src][-1], q, '{}MC31'.format(src))
        srls[dst][0].connections['D'] = '{}MC31'.format(src)

    need_f8 = site.has_feature('BFFMUX.F8') or site.has_feature('BOUTMUX.F8')
    need_f7a = site.has_feature('AFFMUX.F7') or site.has_feature('AOUTMUX.F7')
    need_f7b = site.has_feature('CFFMUX.F7') or site.has_feature('COUTMUX.F7')

    if need_f8:
        need_f7a = True
        need_f7b = True

    for mux in sorted(muxes):
        if mux == 'F7AMUX':
            if not need_f8 and not need_f7a:
                continue
            else:
                bel_type = 'MUXF7'
                opin = 'O'

            f7amux = Bel(bel_type, 'MUXF7A', priority=7)
            f7amux.set_bel('F7AMUX')

            site.connect_internal(f7amux, 'I0', 'BO6')
            site.connect_internal(f7amux, 'I1', 'AO6')
            site.add_sink(f7amux, 'S', 'AX')

            site.add_internal_source(f7amux, opin, 'F7AMUX_O')

            site.add_bel(f7amux)
        elif mux == 'F7BMUX':
            if not need_f8 and not need_f7b:
                continue
            else:
                bel_type = 'MUXF7'
                opin = 'O'

            f7bmux = Bel(bel_type, 'MUXF7B', priority=7)
            f7bmux.set_bel('F7BMUX')

            site.connect_internal(f7bmux, 'I0', 'DO6')
            site.connect_internal(f7bmux, 'I1', 'CO6')
            site.add_sink(f7bmux, 'S', 'CX')

            site.add_internal_source(f7bmux, opin, 'F7BMUX_O')

            site.add_bel(f7bmux)
        elif mux == 'F8MUX':
            if not need_f8:
                continue
            else:
                bel_type = 'MUXF8'
                opin = 'O'

            f8mux = Bel(bel_type, priority=7)

            site.connect_internal(f8mux, 'I0', 'F7BMUX_O')
            site.connect_internal(f8mux, 'I1', 'F7AMUX_O')
            site.add_sink(f8mux, 'S', 'BX')

            site.add_internal_source(f8mux, opin, 'F8MUX_O')

            site.add_bel(f8mux)
        else:
            assert False, mux

    can_have_carry4 = True
    for lut in 'ABCD':
        if site.has_feature(lut + 'O6') or site.has_feature(lut + 'LUT.RAM'):
            can_have_carry4 = False
            break

    if len(srls) != 0:
        can_have_carry4 = False

    if can_have_carry4:
        bel = Bel('CARRY4', priority=1)

        for idx in range(4):
            lut = chr(ord('A') + idx)
            if site.has_feature('CARRY4.{}CY0'.format(lut)):
                source = lut + 'O5'
                site.connect_internal(bel, 'DI[{}]'.format(idx), source)
            else:
                site.add_sink(bel, 'DI[{}]'.format(idx), lut + 'X')

            source = lut + 'O6'

            site.connect_internal(bel, 'S[{}]'.format(idx), source)

            site.add_internal_source(bel, 'O[{}]'.format(idx), lut + '_XOR')

            co_pin = 'CO[{}]'.format(idx)
            if idx == 3:
                site.add_source(bel, co_pin, 'COUT')
            else:
                site.add_internal_source(bel, co_pin, lut + '_CY')

        if site.has_feature('PRECYINIT.AX'):
            site.add_sink(bel, 'CYINIT', 'AX')
            bel.connections['CI'] = 0

        elif site.has_feature('PRECYINIT.C0'):
            bel.connections['CYINIT'] = 0
            bel.connections['CI'] = 0

        elif site.has_feature('PRECYINIT.C1'):
            bel.connections['CYINIT'] = 1
            bel.connections['CI'] = 0

        elif site.has_feature('PRECYINIT.CIN'):
            bel.connections['CYINIT'] = 0
            site.add_sink(bel, 'CI', 'CIN')

        else:
            assert False

        site.add_bel(bel, name='CARRY4')

    ff5_bels = {}
    for lut in 'ABCD':
        if site.has_feature('{}OUTMUX.{}5Q'.format(lut, lut)) or \
                site.has_feature('{}5FFMUX.IN_A'.format(lut)) or \
                site.has_feature('{}5FFMUX.IN_B'.format(lut)):
            # 5FF in use, emit
            name, clk, ce, sr, init = ff_bel(site, lut, ff5=True)
            ff5 = Bel(name, "{}5_{}".format(lut, name))
            ff5_bels[lut] = ff5
            ff5.set_bel(lut + '5FF')

            if site.has_feature('{}5FFMUX.IN_A'.format(lut)):
                site.connect_internal(ff5, 'D', lut + 'O5')
            elif site.has_feature('{}5FFMUX.IN_B'.format(lut)):
                site.add_sink(ff5, 'D', lut + 'X')

            site.add_sink(ff5, clk, "CLK")

            connect_ce_sr(ff5, ce, sr)

            site.add_internal_source(ff5, 'Q', lut + '5Q')
            ff5.parameters['INIT'] = init

            if name in ['LDCE', 'LDPE']:
                ff5.parameters['IS_G_INVERTED'] = IS_C_INVERTED
            else:
                ff5.parameters['IS_C_INVERTED'] = IS_C_INVERTED

            site.add_bel(ff5)

    for lut in 'ABCD':
        name, clk, ce, sr, init = ff_bel(site, lut, ff5=False)
        ff = Bel(name, "{}_{}".format(lut, name))
        ff.set_bel(lut + 'FF')

        if site.has_feature('{}FFMUX.{}X'.format(lut, lut)):
            site.add_sink(ff, 'D', lut + 'X')

        elif lut == 'A' and site.has_feature('AFFMUX.F7'):
            site.connect_internal(ff, 'D', 'F7AMUX_O')

        elif lut == 'C' and site.has_feature('CFFMUX.F7'):
            site.connect_internal(ff, 'D', 'F7BMUX_O')

        elif lut == 'B' and site.has_feature('BFFMUX.F8'):
            site.connect_internal(ff, 'D', 'F8MUX_O')

        elif lut == 'D' and site.has_feature('DFFMUX.MC31'):
            site.connect_internal(ff, 'D', 'AMC31')

        elif site.has_feature('{}FFMUX.O5'.format(lut)):
            site.connect_internal(ff, 'D', lut + 'O5')

        elif site.has_feature('{}FFMUX.O6'.format(lut)):
            site.connect_internal(ff, 'D', lut + 'O6')

        elif site.has_feature('{}FFMUX.CY'.format(lut)):
            assert can_have_carry4
            if lut != 'D':
                site.connect_internal(ff, 'D', lut + '_CY')
            else:
                ff.connections['D'] = 'COUT'
        elif site.has_feature('{}FFMUX.XOR'.format(lut)):
            assert can_have_carry4
            site.connect_internal(ff, 'D', lut + '_XOR')
        else:
            continue

        site.add_source(ff, 'Q', lut + 'Q')
        site.add_sink(ff, clk, "CLK")

        connect_ce_sr(ff, ce, sr)

        ff.parameters['INIT'] = init

        if name in ['LDCE', 'LDPE']:
            ff.parameters['IS_G_INVERTED'] = IS_C_INVERTED
        else:
            ff.parameters['IS_C_INVERTED'] = IS_C_INVERTED

        site.add_bel(ff)

    for lut in 'ABCD':
        if lut + 'O6' in site.internal_sources:
            site.add_output_from_internal(lut, lut + 'O6')

    for lut in 'ABCD':
        output_wire = lut + 'MUX'
        if site.has_feature('{}OUTMUX.{}5Q'.format(lut, lut)):
            site.add_output_from_internal(output_wire, lut + '5Q')

        elif lut == 'A' and site.has_feature('AOUTMUX.F7'):
            site.add_output_from_internal(output_wire, 'F7AMUX_O')

        elif lut == 'C' and site.has_feature('COUTMUX.F7'):
            site.add_output_from_internal(output_wire, 'F7BMUX_O')

        elif lut == 'B' and site.has_feature('BOUTMUX.F8'):
            site.add_output_from_internal(output_wire, 'F8MUX_O')

        elif site.has_feature('{}OUTMUX.O5'.format(lut)):
            site.add_output_from_internal(output_wire, lut + 'O5')

        elif site.has_feature('{}OUTMUX.O6'.format(lut)):
            # Note: There is a dedicated O6 output.  Fixed routing requires
            # treating xMUX.O6 as a routing connection.
            site.add_output_from_output(output_wire, lut)

        elif site.has_feature('{}OUTMUX.CY'.format(lut)):
            assert can_have_carry4
            if lut != 'D':
                site.add_output_from_internal(output_wire, lut + '_CY')
            else:
                site.add_output_from_output(output_wire, 'COUT')

        elif site.has_feature('{}OUTMUX.XOR'.format(lut)):
            assert can_have_carry4
            site.add_output_from_internal(output_wire, lut + '_XOR')
        else:
            continue

    if site.has_feature('DOUTMUX.MC31'):
        site.add_output_from_internal('DMUX', 'AMC31')

    site.set_post_route_cleanup_function(cleanup_slice)
    top.add_site(site)


def process_clb(conn, top, tile_name, features):
    slices = {
        '0': [],
        '1': [],
    }

    for f in features:
        parts = f.feature.split('.')

        if not parts[1].startswith('SLICE'):
            continue

        slices[parts[1][-1]].append(f)

    for s in slices:
        if len(slices[s]) > 0:
            process_slice(top, slices[s])
