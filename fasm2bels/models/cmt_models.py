from .verilog_modeling import Bel, Site, make_inverter_path

# =============================================================================

# A lookup table for content of the TABLE register to get the BANDWIDTH
# setting. Values taken from XAPP888 reference design.
PLL_BANDWIDTH_LOOKUP = {

    # LOW
    0b0010111100: "LOW",
    0b0010011100: "LOW",
    0b0010110100: "LOW",
    0b0010010100: "LOW",
    0b0010100100: "LOW",
    0b0010111000: "LOW",
    0b0010000100: "LOW",
    0b0010011000: "LOW",
    0b0010101000: "LOW",
    0b0010110000: "LOW",
    0b0010001000: "LOW",
    0b0011110000: "LOW",
    # 0b0010010000: "LOW",  # Overlaps with one of "OPTIMIZED"

    # OPTIMIZED and HIGH are the same
    0b0011011100: "OPTIMIZED",
    0b0101111100: "OPTIMIZED",
    0b0111111100: "OPTIMIZED",
    0b0111101100: "OPTIMIZED",
    0b1101011100: "OPTIMIZED",
    0b1110101100: "OPTIMIZED",
    0b1110110100: "OPTIMIZED",
    0b1111110100: "OPTIMIZED",
    0b1111011100: "OPTIMIZED",
    0b1111101100: "OPTIMIZED",
    0b1111110100: "OPTIMIZED",
    0b1111001100: "OPTIMIZED",
    0b1110010100: "OPTIMIZED",
    0b1111010100: "OPTIMIZED",
    0b0111011000: "OPTIMIZED",
    0b0101110000: "OPTIMIZED",
    0b1100000100: "OPTIMIZED",
    0b0100001000: "OPTIMIZED",
    0b0010100000: "OPTIMIZED",
    0b0011010000: "OPTIMIZED",
    0b0010100000: "OPTIMIZED",
    0b0100110000: "OPTIMIZED",
    0b0010010000: "OPTIMIZED",
}

# =============================================================================


def get_pll_site(db, grid, tile, site):
    """ Return the prjxray.tile.Site object for the given PLL site. """
    gridinfo = grid.gridinfo_at_tilename(tile)
    tile_type = db.get_tile_type(gridinfo.tile_type)

    sites = list(tile_type.get_instance_sites(gridinfo))
    assert len(sites) == 1, sites

    return sites[0]


def process_pll(conn, top, tile_name, features):
    """
    Processes the PLL site
    """

    # VCO operating ranges [MHz] (for speed grade -1)
    vco_range = (800.0, 1600.0)
    # Max. CLKIN period [ns]
    max_clkin_period = 52.631

    # Filter only PLL related features
    pll_features = [f for f in features if 'PLLE2.' in f.feature]
    if len(pll_features) == 0:
        return

    # Create the site
    site = Site(
        pll_features,
        get_pll_site(top.db, top.grid, tile=tile_name, site='PLLE2_ADV'))

    # If the PLL is not used then skip the rest
    if not site.has_feature("IN_USE"):
        return

    # Create the PLLE2_ADV bel and add its ports
    pll = Bel('PLLE2_ADV')
    pll.set_bel('PLLE2_ADV')

    for i in range(7):
        site.add_sink(pll, 'DADDR[{}]'.format(i), 'DADDR{}'.format(i), pll.bel,
                      'DADDR{}'.format(i))

    for i in range(16):
        site.add_sink(pll, 'DI[{}]'.format(i), 'DI{}'.format(i), pll.bel,
                      'DI{}'.format(i))

    # Built-in inverters
    pll.parameters['IS_CLKINSEL_INVERTED'] =\
        "1'b1" if site.has_feature('INV_CLKINSEL') else "1'b0"
    pll.parameters['IS_PWRDWN_INVERTED'] =\
        "1'b1" if site.has_feature('ZINV_PWRDWN') else "1'b0"
    pll.parameters['IS_RST_INVERTED'] =\
        "1'b1" if site.has_feature('ZINV_RST') else "1'b0"

    for wire in (
            'CLKINSEL',
            'PWRDWN',
            'RST',
    ):
        site_pips = make_inverter_path(
            wire, pll.parameters['IS_{}_INVERTED'.format(wire)] == "1'b1")
        site.add_sink(pll, wire, wire, pll.bel, wire, site_pips)

    for wire in (
            'DCLK',
            'DEN',
            'DWE',
            'CLKIN1',
            'CLKIN2',
            'CLKFBIN',
    ):
        site.add_sink(pll, wire, wire, pll.bel, wire)

    for wire in (
            'DRDY',
            'LOCKED',
    ):
        site.add_source(pll, wire, wire, pll.bel, wire)

    for i in range(16):
        site.add_source(pll, 'DO[{}]'.format(i), 'DO{}'.format(i), pll.bel,
                        'DO{}'.format(i))

    # Process clock outputs
    clkouts = ['FBOUT'] + ['OUT{}'.format(i) for i in range(6)]

    for clkout in clkouts:
        if site.has_feature('CLK{}_CLKOUT1_OUTPUT_ENABLE'.format(clkout)):

            # Add output source
            site.add_source(pll, 'CLK' + clkout, 'CLK' + clkout, pll.bel,
                            'CLK' + clkout)

            # Calculate the divider and duty cycle
            high_time = site.decode_multi_bit_feature(
                'CLK{}_CLKOUT1_HIGH_TIME'.format(clkout))
            low_time = site.decode_multi_bit_feature(
                'CLK{}_CLKOUT1_LOW_TIME'.format(clkout))

            if site.decode_multi_bit_feature(
                    'CLK{}_CLKOUT2_EDGE'.format(clkout)):
                high_time += 0.5
                low_time = max(0, low_time - 0.5)

            divider = int(high_time + low_time)
            duty = high_time / (low_time + high_time)

            if site.has_feature('CLK{}_CLKOUT2_NO_COUNT'.format(clkout)):
                divider = 1
                duty = 0.5

            if clkout == 'FBOUT':
                vco_m = float(divider)
                pll.parameters['CLKFBOUT_MULT'] = divider
            else:
                pll.parameters['CLK{}_DIVIDE'.format(clkout)] = divider
                pll.parameters['CLK{}_DUTY_CYCLE'.format(
                    clkout)] = "{0:.3f}".format(duty)

            # Phase shift
            delay = site.decode_multi_bit_feature(
                'CLK{}_CLKOUT2_DELAY_TIME'.format(clkout))
            phase = site.decode_multi_bit_feature(
                'CLK{}_CLKOUT1_PHASE_MUX'.format(clkout))

            phase = float(delay) + phase / 8.0  # Delay in VCO cycles
            phase = 360.0 * phase / divider  # Phase of CLK in degrees

            if clkout == 'FBOUT':
                pll.parameters['CLKFBOUT_PHASE'] = "{0:.3f}".format(phase)
            else:
                pll.parameters['CLK{}_PHASE'.format(
                    clkout)] = "{0:.3f}".format(phase)
        else:
            pll.add_unconnected_port('CLK' + clkout, None, output=True)
            pll.map_bel_pin_to_cell_pin(
                bel_name=pll.bel,
                bel_pin='CLK' + clkout,
                cell_pin='CLK' + clkout,
            )

    # Input clock divider
    high_time = site.decode_multi_bit_feature('DIVCLK_DIVCLK_HIGH_TIME')
    low_time = site.decode_multi_bit_feature('DIVCLK_DIVCLK_LOW_TIME')

    divider = high_time + low_time

    if site.has_feature('DIVCLK_DIVCLK_NO_COUNT'):
        divider = 1

    vco_d = float(divider)
    pll.parameters['DIVCLK_DIVIDE'] = divider

    # Compute CLKIN1 and CLKIN2 periods so the VCO frequency derived from
    # it falls within its operation range. This is needed to pass Vivado
    # DRC checks. Those calculations are NOT based on any design constraints!
    clkin_period = (vco_m / vco_d) * (2.0 /
                                      (vco_range[0] + vco_range[1])) * 1e3
    clkin_period = min(clkin_period, max_clkin_period)

    pll.parameters['CLKIN1_PERIOD'] = "{:.3f}".format(clkin_period)
    pll.parameters['CLKIN2_PERIOD'] = "{:.3f}".format(clkin_period)

    # Startup wait
    pll.parameters['STARTUP_WAIT'] = '"TRUE"' if site.has_feature(
        'STARTUP_WAIT') else '"FALSE"'

    # Bandwidth
    table = site.decode_multi_bit_feature('TABLE')
    if table in PLL_BANDWIDTH_LOOKUP:
        pll.parameters['BANDWIDTH'] =\
            '"{}"'.format(PLL_BANDWIDTH_LOOKUP[table])

    # Compensation  TODO: Probably need to rework database tags for those.
    if site.has_feature('COMPENSATION.INTERNAL'):
        pll.parameters['COMPENSATION'] = '"INTERNAL"'
    elif site.has_feature(
            'COMPENSATION.BUF_IN_OR_EXTERNAL_OR_ZHOLD_CLKIN_BUF'):
        pll.parameters['COMPENSATION'] = '"BUF_IN"'
    elif site.has_feature('COMPENSATION.Z_ZHOLD_OR_CLKIN_BUF'):
        pll.parameters['COMPENSATION'] = '"ZHOLD"'
    else:
        # FIXME: This is probably wrong?
        # No path is COMPENSATION = "EXTERNAL" ???
        pll.parameters['COMPENSATION'] = '"INTERNAL"'

    # Add the bel and site
    site.add_bel(pll)
    top.add_site(site)
