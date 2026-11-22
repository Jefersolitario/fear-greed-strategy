
## All configurations: annualised return on committed gross notional, % per year. Net = taker 5 bps + half-spread + funding. Late = every fill one bar later. p placebo = share of 1,000 random-pair portfolios with at least this net PnL.
| configuration | timing | gross | net | net 95% (block bootstrap) | Sharpe net | maker-fee case | spot-fee case | funding | placebo mean net | p placebo | PSR(0) | deflated Sharpe (N=24) | ES 5% day, bps | worst day | worst 5 days | max drawdown |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1h coint e1.5 | late | 3.6 | -2.6 | [-12.2, 7.2] | -0.19 | 2.5 | -4.8 | -0.24 | -7.5 | 0.099 | 0.328 | 0.000 | -135.7 | -1614.5 | -2056.4 | -3722 |
| 1h coint e1.5 | ontime | 7.4 | 1.2 | [-9.0, 11.8] | 0.08 | 6.2 | -1.0 | -0.25 | -6.6 | 0.022 | 0.577 | 0.000 | -136.1 | -1317.4 | -1750.4 | -3323 |
| 1h coint e2.0 | late | 1.7 | -3.1 | [-11.6, 5.5] | -0.27 | 0.8 | -4.8 | -0.23 | -5.8 | 0.198 | 0.257 | 0.000 | -116.3 | -1575.8 | -1837.2 | -4434 |
| 1h coint e2.0 | ontime | 4.3 | -0.6 | [-9.3, 8.5] | -0.05 | 3.4 | -2.2 | -0.23 | -5.1 | 0.065 | 0.455 | 0.000 | -116.5 | -1284.1 | -1512.0 | -3851 |
| 1h coint e2.5 | late | -1.2 | -5.1 | [-12.6, 2.1] | -0.58 | -2.0 | -6.4 | -0.22 | -4.4 | 0.617 | 0.056 | 0.000 | -99.2 | -1376.8 | -1496.3 | -4684 |
| 1h coint e2.5 | ontime | 1.0 | -2.9 | [-10.1, 4.5] | -0.33 | 0.2 | -4.2 | -0.21 | -3.9 | 0.354 | 0.204 | 0.000 | -97.2 | -1147.5 | -1215.1 | -4205 |
| 1h coint vol | late | 1.6 | -3.3 | [-10.8, 4.1] | -0.30 | 0.7 | -5.0 | -0.19 | -6.1 | 0.148 | 0.234 | 0.000 | -104.4 | -1576.3 | -1837.5 | -3920 |
| 1h coint vol | ontime | 4.2 | -0.7 | [-8.2, 7.0] | -0.06 | 3.3 | -2.4 | -0.18 | -5.6 | 0.057 | 0.440 | 0.000 | -104.7 | -1284.5 | -1512.1 | -3061 |
| 1h dist e1.5 | late | -0.1 | -5.3 | [-10.0, -0.6] | -1.02 | -1.0 | -7.2 | -0.12 | -2.5 | 0.783 | 0.008 | 0.000 | -68.3 | -179.9 | -345.4 | -3375 |
| 1h dist e1.5 | ontime | 0.3 | -5.0 | [-9.8, -0.2] | -0.95 | -0.6 | -6.9 | -0.12 | -2.0 | 0.798 | 0.012 | 0.000 | -69.4 | -176.0 | -390.0 | -3539 |
| 1h dist e2.0 | late | -0.2 | -4.3 | [-8.3, -0.3] | -0.94 | -0.9 | -5.8 | -0.05 | -2.6 | 0.714 | 0.013 | 0.000 | -60.1 | -126.4 | -261.2 | -2966 |
| 1h dist e2.0 | ontime | 0.1 | -4.0 | [-8.4, 0.3] | -0.87 | -0.6 | -5.6 | -0.05 | -2.4 | 0.712 | 0.020 | 0.000 | -60.3 | -128.9 | -315.9 | -3024 |
| 1h dist e2.5 | late | 0.9 | -2.4 | [-5.7, 1.1] | -0.63 | 0.4 | -3.6 | 0.03 | -2.1 | 0.541 | 0.068 | 0.000 | -49.2 | -127.4 | -214.9 | -2370 |
| 1h dist e2.5 | ontime | 1.3 | -2.0 | [-5.5, 1.5] | -0.54 | 0.8 | -3.3 | 0.03 | -2.1 | 0.506 | 0.102 | 0.000 | -48.6 | -120.6 | -214.8 | -2312 |
| 1h dist vol | late | -0.7 | -4.7 | [-8.5, -0.9] | -1.07 | -1.3 | -6.2 | -0.05 | -3.1 | 0.728 | 0.006 | 0.000 | -58.6 | -136.7 | -245.5 | -2859 |
| 1h dist vol | ontime | -0.5 | -4.5 | [-8.5, -0.6] | -1.02 | -1.2 | -6.1 | -0.05 | -2.7 | 0.755 | 0.008 | 0.000 | -58.6 | -126.1 | -300.2 | -2910 |
| 5mA coint e2.0 | late | 10.6 | -27.0 | [-42.8, -7.9] | -3.38 | 2.5 | -47.8 | 0.16 | -34.1 | 0.124 | 0.001 | 0.000 | -103.5 | -166.4 | -257.3 | -2795 |
| 5mA coint e2.0 | ontime | 11.1 | -26.5 | [-42.3, -7.6] | -3.27 | 3.0 | -47.3 | 0.21 | -32.8 | 0.151 | 0.001 | 0.000 | -104.3 | -161.6 | -272.2 | -2789 |
| 5mA dist e2.0 | late | -2.2 | -31.8 | [-41.8, -22.2] | -9.26 | -8.9 | -49.2 | 0.28 | -20.2 | 0.945 | 0.000 | 0.000 | -53.2 | -77.7 | -170.0 | -3138 |
| 5mA dist e2.0 | ontime | -2.1 | -31.7 | [-41.9, -22.1] | -9.35 | -8.7 | -49.1 | 0.28 | -18.3 | 0.966 | 0.000 | 0.000 | -52.5 | -77.7 | -164.2 | -3130 |
| 5mB coint e2.0 | late | -11.2 | -13.2 | [-22.7, -4.4] | -2.47 | -11.1 | -14.6 | 0.63 | -11.0 | 0.631 | 0.007 | 0.000 | -75.8 | -213.3 | -299.8 | -1178 |
| 5mB coint e2.0 | ontime | -11.3 | -13.3 | [-23.0, -4.3] | -2.47 | -11.2 | -14.7 | 0.62 | -11.1 | 0.637 | 0.007 | 0.000 | -76.6 | -229.1 | -317.2 | -1206 |
| 5mB dist e2.0 | late | -5.0 | -7.2 | [-13.0, -1.4] | -1.86 | -5.5 | -8.5 | 0.02 | -1.6 | 0.828 | 0.056 | 0.000 | -49.9 | -83.6 | -141.5 | -718 |
| 5mB dist e2.0 | ontime | -5.0 | -7.2 | [-13.0, -1.4] | -1.87 | -5.5 | -8.5 | 0.01 | -1.5 | 0.837 | 0.055 | 0.000 | -49.3 | -78.7 | -143.5 | -714 |

## Net PnL by calendar year, % of committed gross notional (taker costs and funding); placebo mean in brackets

| configuration (1h) | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| 1h_coint_e1.5_late | -7.6 (-17.7) | 22.1 (1.7) | 0.8 (-4.9) | -14.5 (-7.9) | -5.1 (-11.9) | -10.5 (-1.7) |
| 1h_coint_e1.5_ontime | -2.7 (-16.3) | 29.6 (3.3) | 2.4 (-3.9) | -13.6 (-7.5) | -4.1 (-12.4) | -5.0 (-0.4) |
| 1h_coint_e2.0_late | -2.8 (-12.4) | 20.1 (0.9) | -2.4 (-3.8) | -15.3 (-7.2) | -3.5 (-8.9) | -13.7 (-1.3) |
| 1h_coint_e2.0_ontime | 0.4 (-11.5) | 24.5 (2.1) | -0.7 (-3.1) | -15.1 (-6.9) | -2.7 (-9.5) | -9.6 (-0.2) |
| 1h_coint_e2.5_late | -4.4 (-8.4) | 13.6 (0.1) | -2.5 (-2.3) | -14.8 (-5.9) | -3.5 (-6.6) | -17.5 (-1.5) |
| 1h_coint_e2.5_ontime | -1.8 (-7.7) | 19.3 (0.8) | -2.7 (-1.8) | -13.8 (-5.7) | -2.5 (-6.9) | -14.8 (-0.5) |
| 1h_coint_vol_late | -3.2 (-12.8) | 15.9 (-0.5) | -5.7 (-3.0) | -11.4 (-6.9) | -2.2 (-10.0) | -12.1 (-1.6) |
| 1h_coint_vol_ontime | -1.0 (-12.1) | 19.0 (0.5) | -3.3 (-2.4) | -10.6 (-6.7) | -0.6 (-10.3) | -7.7 (-0.8) |
| 1h_dist_e1.5_late | -1.9 (-0.7) | -0.9 (7.0) | 1.3 (-4.9) | -7.9 (-2.0) | -10.1 (-13.0) | -10.5 (-0.3) |
| 1h_dist_e1.5_ontime | -0.4 (0.6) | 0.8 (8.0) | 2.4 (-4.5) | -8.7 (-1.8) | -10.4 (-13.2) | -11.8 (-0.3) |
| 1h_dist_e2.0_late | -0.1 (-3.5) | -1.2 (4.4) | 3.7 (-4.0) | -6.3 (-1.8) | -11.4 (-9.9) | -8.9 (-0.1) |
| 1h_dist_e2.0_ontime | 1.0 (-2.9) | -1.0 (5.0) | 4.8 (-3.4) | -7.4 (-1.6) | -11.0 (-10.3) | -9.3 (-0.1) |
| 1h_dist_e2.5_late | 1.6 (-2.9) | 2.7 (2.3) | 4.0 (-3.1) | -4.5 (-1.1) | -8.9 (-6.0) | -8.3 (-1.1) |
| 1h_dist_e2.5_ontime | 1.3 (-2.5) | 3.6 (2.5) | 5.0 (-2.7) | -4.2 (-1.3) | -8.6 (-6.5) | -8.6 (-1.2) |
| 1h_dist_vol_late | -1.6 (-3.9) | -2.3 (2.0) | 3.0 (-4.1) | -6.0 (-1.0) | -11.3 (-10.8) | -8.4 (0.3) |
| 1h_dist_vol_ontime | -0.5 (-3.2) | -2.4 (2.7) | 3.9 (-3.5) | -7.3 (-0.6) | -10.8 (-11.0) | -8.6 (0.2) |

| configuration (5mA) | 2025 | 2026 |
|---|---|---|
| 5mA_coint_e2.0_late | -3.7 (-2.9) | -22.9 (-30.7) |
| 5mA_coint_e2.0_ontime | -3.5 (-3.0) | -22.6 (-29.3) |
| 5mA_dist_e2.0_late | -2.0 (-3.1) | -29.3 (-16.8) |
| 5mA_dist_e2.0_ontime | -1.8 (-3.1) | -29.5 (-15.0) |

| configuration (5mB) | 2026 |
|---|---|
| 5mB_coint_e2.0_late | -10.8 (-9.0) |
| 5mB_coint_e2.0_ontime | -10.9 (-9.1) |
| 5mB_dist_e2.0_late | -5.9 (-1.3) |
| 5mB_dist_e2.0_ontime | -5.9 (-1.2) |

## Split in time (hourly): selection = days before 2024-01-01 (1035 days), evaluation = after (1035 days)
| | configuration | Sharpe net | net % per year |
|---|---|---|---|
| best on selection | 1h_coint_e1.5_ontime | 1.03 | 10.3 |
| the same on evaluation | 1h_coint_e1.5_ontime | -0.45 | -8.0 [-22.1, 6.6], p placebo 0.575 |

| configuration | Sharpe selection | Sharpe evaluation | net % per year, evaluation |
|---|---|---|---|
| 1h_coint_e1.5_late | 0.55 | -0.64 | -10.6 |
| 1h_coint_e1.5_ontime | 1.03 | -0.45 | -8.0 |
| 1h_coint_e2.0_late | 0.64 | -0.82 | -11.5 |
| 1h_coint_e2.0_ontime | 1.00 | -0.68 | -9.7 |
| 1h_coint_e2.5_late | 0.35 | -1.20 | -12.6 |
| 1h_coint_e2.5_ontime | 0.74 | -1.10 | -11.0 |
| 1h_coint_vol_late | 0.34 | -0.66 | -9.1 |
| 1h_coint_vol_ontime | 0.68 | -0.48 | -6.6 |
| 1h_dist_e1.5_late | -0.08 | -2.35 | -10.0 |
| 1h_dist_e1.5_ontime | 0.16 | -2.50 | -10.9 |
| 1h_dist_e2.0_late | 0.16 | -2.54 | -9.4 |
| 1h_dist_e2.0_ontime | 0.32 | -2.57 | -9.8 |
| 1h_dist_e2.5_late | 0.67 | -2.48 | -7.6 |
| 1h_dist_e2.5_ontime | 0.80 | -2.44 | -7.6 |
| 1h_dist_vol_late | -0.06 | -2.57 | -9.1 |
| 1h_dist_vol_ontime | 0.07 | -2.62 | -9.4 |

## Best of 16 configurations against the best-of-16 random-pair placebo [1h]: best Sharpe 0.08 (1h_coint_e1.5_ontime); placebo best-of median -0.04, 95th percentile 0.53; p = 0.368. Best net PnL 659 bps (1h_coint_e1.5_ontime), p = 0.297

## Best of 4 configurations against the best-of-4 random-pair placebo [5mA]: best Sharpe -3.27 (5mA_coint_e2.0_ontime); placebo best-of median -1.74, 95th percentile -0.58; p = 0.983. Best net PnL -2613 bps (5mA_coint_e2.0_ontime), p = 0.897

## Best of 4 configurations against the best-of-4 random-pair placebo [5mB]: best Sharpe -1.86 (5mB_dist_e2.0_late); placebo best-of median -0.14, 95th percentile 1.18; p = 0.995. Best net PnL -589 bps (5mB_dist_e2.0_late), p = 0.871

## Pairs selected most often [1h, dist]: 932 distinct pairs in 69 windows; 35% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| BNB / BTC | 11 | 2801 | 2243 | 2576 |
| BTC / ETH | 8 | 1151 | 877 | 998 |
| EOS / ETC | 7 | 6286 | 5258 | 4777 |
| DOT / VET | 7 | 2163 | 1797 | 2532 |
| ATOM / DOT | 7 | 580 | 190 | 216 |
| ETH / LINK | 7 | 832 | 132 | -458 |
| LTC / XRP | 7 | -948 | -1303 | -1056 |
| ADA / DOT | 7 | -1275 | -1563 | -607 |
| BTC / LTC | 7 | -3458 | -3621 | -4010 |
| BCH / EOS | 6 | 3403 | 2966 | 2374 |
| FIL / SHIB | 6 | 3211 | 2709 | 1881 |
| BCH / LTC | 6 | 830 | 385 | -11 |

## Pairs selected most often [1h, coint]: 1294 distinct pairs in 69 windows; 37% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| ATOM / GALA | 4 | 177 | -103 | -358 |
| ATOM / FTM | 3 | 2419 | 2117 | 2540 |
| DOGE / SHIB | 3 | 414 | 191 | -58 |
| ATOM / SHIB | 3 | 368 | 11 | -301 |
| FET / RENDER | 3 | 267 | -31 | 227 |
| ENJ / MANA | 3 | -425 | -715 | -639 |
| ADA / LINK | 3 | -723 | -875 | -1195 |
| DOT / NEAR | 3 | -1546 | -1887 | -1916 |
| CTXC / GXS | 2 | 5776 | 5642 | 5248 |
| KAVA / LRC | 2 | 5268 | 4911 | 5130 |
| FIL / ICP | 2 | 3910 | 3640 | 3098 |
| MEME / SAND | 2 | 3202 | 3024 | 3342 |

## Pairs selected most often [5mA, dist]: 400 distinct pairs in 144 windows; 25% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| BNB / BTC | 79 | 781 | -1314 | -1582 |
| BTC / ETH | 70 | 1901 | -76 | -54 |
| ETH / SOL | 54 | -889 | -2459 | -2467 |
| ETH / LINK | 52 | -208 | -1935 | -2214 |
| AVAX / LINK | 48 | 324 | -1931 | -2354 |
| BTC / XRP | 47 | 862 | -507 | -804 |
| LINK / SOL | 46 | 1248 | -730 | -941 |
| DOGE / XRP | 45 | 612 | -665 | -759 |
| ADA / DOGE | 44 | 838 | -946 | -644 |
| BNB / SOL | 41 | -19 | -1314 | -1000 |
| ADA / LINK | 41 | -372 | -2089 | -1929 |
| DOGE / SOL | 40 | 48 | -1117 | -1241 |

## Pairs selected most often [5mA, coint]: 1192 distinct pairs in 144 windows; 36% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| DOGE / PEPE | 37 | 935 | -816 | -886 |
| ADA / PEPE | 30 | 2099 | 329 | 136 |
| AVAX / PEPE | 30 | 1678 | -258 | -654 |
| PEPE / XRP | 30 | -85 | -1388 | -1271 |
| LINK / PEPE | 29 | 4194 | 1933 | 1436 |
| PEPE / SOL | 26 | -319 | -1583 | -1361 |
| PEPE / SUI | 25 | 811 | -669 | -1115 |
| LTC / PEPE | 20 | 2240 | 1089 | 1019 |
| BNB / PEPE | 20 | -1772 | -2742 | -2712 |
| BTC / PEPE | 17 | 1225 | 402 | 396 |
| ETH / PEPE | 17 | -66 | -1058 | -663 |
| PEPE / TAO | 16 | 1879 | 860 | 949 |

## Pairs selected most often [5mB, dist]: 107 distinct pairs in 10 windows; 28% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| DOGE / XRP | 6 | 928 | 733 | 942 |
| BTC / XRP | 5 | 1429 | 1234 | 1295 |
| BNB / BTC | 5 | 745 | 617 | 589 |
| LINK / SOL | 5 | -6 | -144 | -123 |
| ADA / AVAX | 4 | 1777 | 1648 | 1781 |
| LTC / XRP | 4 | 966 | 752 | 772 |
| BNB / XRP | 4 | 493 | 380 | 294 |
| BTC / LINK | 4 | 99 | -109 | -119 |
| AVAX / LINK | 4 | -188 | -376 | -362 |
| AVAX / SOL | 4 | -516 | -626 | -641 |
| ADA / XRP | 4 | -1494 | -1600 | -1555 |
| BNB / ETH | 4 | -1593 | -1687 | -1585 |

## Pairs selected most often [5mB, coint]: 179 distinct pairs in 10 windows; 32% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| BTC / SOL | 3 | 388 | 263 | 209 |
| LTC / SUI | 2 | 1077 | 874 | 1064 |
| LINK / LTC | 2 | 681 | 420 | 424 |
| AVAX / XRP | 2 | 460 | 356 | 509 |
| AVAX / SUI | 2 | 437 | 323 | 467 |
| LTC / SOL | 2 | 352 | 228 | 116 |
| SUI / XRP | 2 | 128 | 66 | 110 |
| ETH / SOL | 2 | 38 | -9 | -13 |
| LINK / SOL | 2 | -199 | -239 | -275 |
| DOGE / SOL | 2 | -302 | -358 | -396 |
| AVAX / BTC | 2 | -326 | -422 | -530 |
| LTC / PEPE | 2 | -335 | -489 | -472 |

## Hindsight check (hourly, base rule). Net % per year on committed gross notional
| method | selected in advance | the 20 best pairs of each window, chosen afterwards |
|---|---|---|
| dist | -4.0 | 553.3 |
| coint | -0.6 | 494.3 |

| method | rank correlation of a pair's net PnL in consecutive windows [95%] | next-window net PnL of this window's top decile, bps | of the other pairs | difference 95% | mean net PnL of all pairs per window, bps | share of pair-windows with net > 0 |
|---|---|---|---|---|---|---|
| dist | -0.000 [-0.014, 0.015] | -57.2 | -43.1 | [-60.7, 33.6] | -37.3 | 26% |
| coint | -0.010 [-0.018, -0.002] | -65.3 | -74.1 | [-30.8, 53.4] | -71.2 | 29% |

## Trades of the selected pairs (base rule). PnL in bps of one leg's notional
| bar | method | timing | trades | mean gross | mean cost | mean funding | mean net | share net > 0 | closed at 0 / stop / window end / delisted | median hold, hours | median volume of the thinner leg in the signal bar, USD | 10th percentile | both legs had a perpetual |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1h | dist | ontime | 1771 | 0.9 | 51.9 | -0.64 | -51.6 | 43% | 36% / 50% / 14% / 0% | 85.0 | 699407 | 130081 | 94% |
| 1h | dist | late | 1770 | -2.4 | 51.9 | -0.63 | -54.9 | 44% | 36% / 50% / 14% / 0% | 85.0 | 697229 | 130059 | 94% |
| 1h | coint | ontime | 1893 | 51.0 | 54.8 | -2.80 | -6.7 | 48% | 40% / 48% / 12% / 0% | 75.0 | 478268 | 73352 | 78% |
| 1h | coint | late | 1893 | 20.4 | 54.8 | -2.80 | -37.2 | 49% | 40% / 47% / 12% / 0% | 75.0 | 478268 | 73352 | 78% |
| 5mA | dist | ontime | 3434 | -2.4 | 34.4 | 0.32 | -36.4 | 44% | 35% / 43% / 22% / 0% | 11.8 | 93994 | 14985 | 95% |
| 5mA | dist | late | 3431 | -2.5 | 34.4 | 0.32 | -36.6 | 43% | 35% / 43% / 22% / 0% | 11.8 | 94107 | 15007 | 95% |
| 5mA | coint | ontime | 4104 | 10.7 | 36.3 | 0.20 | -25.5 | 45% | 41% / 47% / 13% / 0% | 7.4 | 48417 | 5997 | 94% |
| 5mA | coint | late | 4104 | 10.2 | 36.3 | 0.15 | -26.0 | 45% | 41% / 47% / 13% / 0% | 7.4 | 48417 | 5997 | 94% |
| 5mB | dist | ontime | 214 | -76.8 | 33.5 | 0.23 | -110.1 | 39% | 31% / 51% / 18% / 0% | 117.9 | 162497 | 20336 | 99% |
| 5mB | dist | late | 214 | -76.7 | 33.5 | 0.24 | -110.0 | 40% | 31% / 51% / 18% / 0% | 117.9 | 162497 | 20336 | 99% |
| 5mB | coint | ontime | 237 | -156.4 | 36.4 | 8.65 | -184.2 | 38% | 32% / 46% / 21% / 0% | 109.6 | 76112 | 5928 | 93% |
| 5mB | coint | late | 237 | -154.7 | 36.4 | 8.70 | -182.5 | 38% | 32% / 46% / 21% / 0% | 109.5 | 76112 | 5928 | 93% |

## Cointegration tests per window, Benjamini-Hochberg at 5% over all pairs of the universe
| bar | windows | pairs per window (median) | pairs passing BH (median, mean, max) | windows with none | selected pairs that pass (mean of 20) |
|---|---|---|---|---|---|
| 1h | 69 | 4371 | 8, 39.0, 316 | 13 | 10.5 |
| 5mA | 144 | 435 | 1, 7.3, 145 | 69 | 5.8 |
| 5mB | 10 | 364 | 2, 8.0, 62 | 4 | 4.5 |

## Overshoot and reversion after a Bitcoin shock: buy the 10 coins that fell most against beta x Bitcoin, short beta x Bitcoin, from one to two hours after the shock. Mean per event, bps of the coin leg [95%, bootstrap over weeks]
| events | hold | n | mean abnormal return of all coins in the shock window | of the 10 picked | gross | net taker | net maker-fee case | share of events net > 0 | placebo gross (random hours) | p vs placebo | cross-sectional slope of later return on shock-window abnormal return | all coins hedged, gross |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_1min_down | 4 h | 104 | -14.5 | -334.5 | 34.8 [-4.5, 80.7] | -8.0 [-46.3, 37.8] | 26.9 [-13.1, 73.5] | 49% | 2.7 | 0.010 | -0.043 [-0.092, 0.007] | 17.7 [-11.1, 48.6] |
| A_1min_down | 24 h | 104 | -14.5 | -334.5 | 112.2 [42.3, 183.5] | 73.3 [2.0, 142.8] | 108.2 [38.5, 180.3] | 52% | -11.0 | 0.001 | -0.081 [-0.203, 0.036] | 63.5 [0.3, 133.8] |
| A_1min_down | 72 h | 104 | -14.5 | -334.5 | 67.5 [-108.3, 236.2] | 36.4 [-138.5, 200.9] | 71.3 [-100.0, 232.1] | 50% | -49.6 | 0.030 | -0.151 [-0.334, 0.025] | 84.0 [-84.4, 258.7] |
| B_hourly_down | 4 h | 118 | 6.7 | -334.3 | 51.7 [-1.1, 101.1] | 8.3 [-47.0, 58.0] | 43.6 [-12.2, 95.2] | 55% | 2.7 | 0.000 | -0.075 [-0.117, -0.031] | 29.5 [-6.3, 63.6] |
| B_hourly_down | 24 h | 118 | 6.7 | -334.3 | 122.4 [14.1, 225.2] | 82.3 [-29.4, 184.8] | 117.6 [10.3, 218.7] | 58% | -11.0 | 0.000 | -0.126 [-0.239, -0.011] | 81.3 [5.7, 157.9] |
| B_hourly_down | 72 h | 118 | 6.7 | -334.3 | 95.0 [-81.4, 267.8] | 64.1 [-110.2, 239.1] | 99.4 [-74.5, 273.7] | 53% | -49.6 | 0.008 | -0.186 [-0.365, -0.018] | 70.9 [-74.5, 208.9] |
| A_1min_up_mirror | 4 h | 100 | -65.0 | 312.6 | -12.0 [-53.0, 24.2] | -57.7 [-98.4, -21.3] | -22.9 [-62.4, 14.6] | 43% | 2.7 | 0.853 | 0.008 [-0.058, 0.079] | 10.0 [-18.2, 43.6] |
| A_1min_up_mirror | 24 h | 100 | -65.0 | 312.6 | 20.8 [-80.3, 128.2] | -31.7 [-135.3, 83.4] | 3.2 [-100.0, 113.7] | 48% | -11.0 | 0.193 | -0.073 [-0.229, 0.073] | -18.1 [-96.8, 59.0] |
| A_1min_up_mirror | 72 h | 100 | -65.0 | 312.6 | 85.1 [-97.3, 266.7] | 14.4 [-184.8, 188.8] | 49.3 [-130.7, 228.6] | 54% | -49.6 | 0.021 | -0.045 [-0.266, 0.165] | -11.1 [-160.6, 152.1] |
| B_hourly_up_mirror | 4 h | 123 | -118.6 | 287.8 | 22.2 [-16.2, 60.7] | -21.7 [-59.1, 18.6] | 12.8 [-25.8, 52.4] | 39% | 2.7 | 0.057 | -0.055 [-0.109, 0.005] | -3.6 [-41.5, 27.1] |
| B_hourly_up_mirror | 24 h | 123 | -118.6 | 287.8 | -16.6 [-92.7, 60.0] | -63.7 [-141.9, 13.7] | -29.2 [-104.6, 48.8] | 41% | -11.0 | 0.567 | -0.018 [-0.121, 0.089] | 18.3 [-42.8, 77.0] |
| B_hourly_up_mirror | 72 h | 123 | -118.6 | 287.8 | -187.4 [-327.2, -44.6] | -244.1 [-385.8, -98.3] | -209.6 [-354.4, -64.3] | 38% | -49.6 | 0.993 | -0.031 [-0.221, 0.157] | 145.8 [33.9, 251.5] |

| events | hold | net, early part (n) | net, late part (n) | median net | worst event |
|---|---|---|---|---|---|
| A_1min_down | 4 h | -12.7 (75) | 4.3 (29) | -5.7 | -777.7 |
| A_1min_down | 24 h | 74.4 (75) | 70.5 (29) | 21.8 | -917.1 |
| A_1min_down | 72 h | 55.2 (75) | -12.2 (29) | -8.5 | -1946.2 |
| B_hourly_down | 4 h | 11.8 (85) | -0.9 (33) | 21.2 | -1678.4 |
| B_hourly_down | 24 h | 76.2 (85) | 98.1 (33) | 37.1 | -2336.6 |
| B_hourly_down | 72 h | 110.6 (85) | -55.6 (33) | 48.9 | -4387.5 |
| A_1min_up_mirror | 4 h | -34.4 (61) | -94.2 (39) | -30.9 | -874.3 |
| A_1min_up_mirror | 24 h | -62.3 (61) | 16.0 (39) | -16.4 | -1654.5 |
| A_1min_up_mirror | 72 h | -32.5 (61) | 87.8 (39) | 60.4 | -2484.7 |
| B_hourly_up_mirror | 4 h | -6.6 (88) | -59.8 (35) | -36.4 | -874.3 |
| B_hourly_up_mirror | 24 h | -54.5 (88) | -86.7 (35) | -70.9 | -1464.8 |
| B_hourly_up_mirror | 72 h | -287.2 (88) | -135.7 (35) | -205.3 | -3433.0 |

## Speed (prior P1): the same rule filled on time and one bar late; % per year on committed gross notional
| configuration | gross on time | gross late | net on time | net late | net lost by one bar of delay | Sharpe net on time | Sharpe net late |
|---|---|---|---|---|---|---|---|
| 1h_coint_e1.5 | 7.4 | 3.6 | 1.2 | -2.6 | 3.8 | 0.08 | -0.19 |
| 1h_coint_e2.0 | 4.3 | 1.7 | -0.6 | -3.1 | 2.5 | -0.05 | -0.27 |
| 1h_coint_e2.5 | 1.0 | -1.2 | -2.9 | -5.1 | 2.2 | -0.33 | -0.58 |
| 1h_coint_vol | 4.2 | 1.6 | -0.7 | -3.3 | 2.6 | -0.06 | -0.30 |
| 1h_dist_e1.5 | 0.3 | -0.1 | -5.0 | -5.3 | 0.3 | -0.95 | -1.02 |
| 1h_dist_e2.0 | 0.1 | -0.2 | -4.0 | -4.3 | 0.3 | -0.87 | -0.94 |
| 1h_dist_e2.5 | 1.3 | 0.9 | -2.0 | -2.4 | 0.3 | -0.54 | -0.63 |
| 1h_dist_vol | -0.5 | -0.7 | -4.5 | -4.7 | 0.1 | -1.02 | -1.07 |
| 5mA_coint_e2.0 | 11.1 | 10.6 | -26.5 | -27.0 | 0.5 | -3.27 | -3.38 |
| 5mA_dist_e2.0 | -2.1 | -2.2 | -31.7 | -31.8 | 0.1 | -9.35 | -9.26 |
| 5mB_coint_e2.0 | -11.3 | -11.2 | -13.3 | -13.2 | -0.1 | -2.47 | -2.47 |
| 5mB_dist_e2.0 | -5.0 | -5.0 | -7.2 | -7.2 | -0.0 | -1.87 | -1.86 |

## Trade size. Share of the signal bar's quote volume (thinner leg) that one leg of the trade would be
| bar | method | trades | median volume of the thinner leg in the signal bar, USD | 1,000 USD as a share of it (median) | trades where 1,000 USD is above 1% of it | 10,000 USD as a share (median) | trades where 10,000 USD is above 1% |
|---|---|---|---|---|---|---|---|
| 1h | dist | 1771 | 699407 | 0.143% | 6.9% | 1.43% | 61.5% |
| 1h | coint | 1893 | 478268 | 0.209% | 13.7% | 2.09% | 73.2% |
| 5mA | dist | 3434 | 93994 | 1.064% | 51.5% | 10.64% | 91.3% |
| 5mA | coint | 4104 | 48417 | 2.065% | 68.8% | 20.65% | 97.1% |
| 5mB | dist | 214 | 162497 | 0.616% | 40.7% | 6.16% | 89.3% |
| 5mB | coint | 237 | 76112 | 1.314% | 57.8% | 13.14% | 96.2% |

(no order-book snapshot yet: run s2_depth.py)

wrote /home/runner/work/fear-greed-strategy/fear-greed-strategy/research/btc-alts/out/p2/summary.json
