"""One colour palette for every figure, so the papers look consistent.

``apply()`` sets matplotlib's default colour cycle and a light, clean axis style;
the named colours are for figures that pick colours explicitly.
"""
# Inspired by Argentina: celeste (flag), navy (night sky of the Andes), malbec, the
# terracotta of the Quebrada, Patagonian lake green, jacaranda, Sol de Mayo gold.
# Every colour has >= 4.5:1 contrast on white except GOLD (3.8:1), so all pass WCAG 1.4.11
# (3:1 for graphics) and most pass 1.4.3 (4.5:1 for text).
NAVY = "#0B2545"        # reference / simulation (Palace)       15.4:1
AZURE = "#1F78B4"       # celeste, darkened for contrast          4.8:1
TURQUOISE = "#0F766E"   # Patagonian green, second simulator (CST) 5.5:1
PINK = "#B3173F"        # malbec                                  6.8:1
ORANGE = "#C2570C"      # terracotta                              4.5:1
VIOLET = "#6D3FA0"      # jacaranda                               7.3:1
SLATE = "#5B6475"       #                                         6.0:1
LILAC = "#D9D4EC"       # fills only ("no data / other")
GOLD = "#A67C00"        # Sol de Mayo                             3.8:1

CYCLE = [AZURE, PINK, ORANGE, TURQUOISE, VIOLET, NAVY, GOLD, SLATE]


def apply() -> None:
    import matplotlib as mpl
    from cycler import cycler
    mpl.rcParams.update({
        "axes.prop_cycle": cycler(color=CYCLE),
        "axes.edgecolor": "#444a66",
        "axes.labelcolor": "#222640",
        "xtick.color": "#444a66",
        "ytick.color": "#444a66",
        "grid.color": "#c9cde0",
        "axes.titleweight": "semibold",
    })
