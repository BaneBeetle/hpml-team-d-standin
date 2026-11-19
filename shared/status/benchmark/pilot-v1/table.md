# Benchmark pilot-v1: stand-in pilot table

Local test fixture (source: standin). Settings of every game: its run folder's run_settings.json.

## Every episode

| Policy | Episode | Outcome | Game min | Wall s | Policy status | Predicts | No-order share | Orders | Dropped by widget | Without engine callback | p50 / p95 ms | Killed / lost value | Max metal income | Run folder |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| builtin-barb | simple-1 | cap | 20.0 | 206 | - | - | - | - | - | - | - / - | 12705 / 4528 | 105.2 | record_20261118_165204 |
| builtin-barb | simple-2 | win | 12.4 | 133 | - | - | - | - | - | - | - / - | 9092 / 1528 | 70.3 | record_20261118_165532 |
| builtin-barb | simple-3 | cap | 20.0 | 214 | - | - | - | - | - | - | - / - | 13919 / 5913 | 118.4 | record_20261118_165748 |
| builtin-barb | barb-easy-1 | cap | 20.0 | 149 | - | - | - | - | - | - | - / - | 3181 / 1788 | 97.0 | record_20261118_170125 |
| builtin-barb | barb-easy-2 | cap | 20.0 | 161 | - | - | - | - | - | - | - / - | 8124 / 4677 | 127.3 | record_20261118_170357 |
| builtin-barb | barb-easy-3 | win | 13.4 | 103 | - | - | - | - | - | - | - / - | 7040 / 2734 | 75.8 | record_20261118_170640 |
| scripted | simple-1 | loss | 5.2 | 66 | policy_error | 549 | 0.996 | 2 | 0 | 0.000 | 19.3 / 30.3 | 352 / 3288 | 2 | game_20261118_162401 |
| scripted | simple-2 | loss | 5.6 | 61 | policy_error | 566 | 0.996 | 2 | 0 | 0.000 | 18.0 / 25.3 | 0 / 3288 | 2 | game_20261118_162511 |
| scripted | simple-3 | loss | 5.0 | 57 | policy_error | 513 | 0.996 | 2 | 0 | 0.000 | 18.2 / 24.7 | 138 / 3288 | 2 | game_20261118_162616 |
| scripted | barb-easy-1 | cap | 20.0 | 161 | answered_until_stopped | 2285 | 0.999 | 2 | 0 | 0.000 | 18.9 / 29.4 | 0 / 0 | 2 | game_20261118_162716 |
| scripted | barb-easy-2 | cap | 20.0 | 140 | answered_until_stopped | 2186 | 0.999 | 2 | 0 | 0.000 | 18.2 / 26.4 | 0 / 0 | 2 | game_20261118_163001 |
| scripted | barb-easy-3 | loss | 16.7 | 147 | policy_error | 1855 | 0.999 | 2 | 0 | 0.000 | 18.8 / 30.2 | 0 / 3288 | 2 | game_20261118_163226 |
| standin-human-v1 | simple-1 | cap | 20.0 | 166 | answered_until_stopped | 2012 | 0.000 | 2012 | 155 | 0.790 | 24.4 / 49.1 | 1290 / 0 | 2 | game_20261118_171753 |
| standin-human-v1 | simple-2 | cap | 20.0 | 160 | answered_until_stopped | 1887 | 0.000 | 1887 | 164 | 0.785 | 24.1 / 43.8 | 5665 / 0 | 2 | game_20261118_172047 |
| standin-human-v1 | simple-3 | cap | 20.0 | 213 | answered_until_stopped | 2013 | 0.000 | 2013 | 187 | 0.813 | 32.5 / 61.0 | 1003 / 0 | 2 | game_20261118_172334 |
| standin-human-v1 | barb-easy-1 | cap | 20.0 | 226 | answered_until_stopped | 2091 | 0.000 | 2091 | 189 | 0.837 | 33.9 / 63.8 | 0 / 0 | 2 | game_20261118_172714 |
| standin-human-v1 | barb-easy-2 | cap | 20.0 | 184 | answered_until_stopped | 1985 | 0.000 | 1985 | 200 | 0.836 | 29.7 / 51.2 | 0 / 0 | 2 | game_20261118_173111 |
| standin-human-v1 | barb-easy-3 | cap | 20.0 | 128 | policy_timeout | 617 | 0.000 | 617 | 45 | 0.802 | 29.8 / 56.5 | 0 / 0 | 2.4 | game_20261118_173424 |
| unit-barb-v1a | simple-1 | loss | 6.1 | 59 | policy_timeout | 1 | 0.000 | 1 | 0 | 0.000 | 89.3 / 89.3 | 630 / 3192 | 4.3 | game_20261118_174612 |
| unit-barb-v1a | simple-2 | loss | 8.9 | 69 | answered_until_stopped | 1091 | 0.883 | 128 | 0 | 0.008 | 15.5 / 23.7 | 1989 / 4449 | 13.2 | game_20261118_174718 |
| unit-barb-v1a | simple-3 | cap | 20.0 | 149 | answered_until_stopped | 2124 | 0.919 | 173 | 1 | 0.017 | 18.8 / 31.2 | 5506 / 2521 | 17.2 | game_20261118_174832 |
| unit-barb-v1a | barb-easy-1 | loss | 11.2 | 101 | answered_until_stopped | 1411 | 0.841 | 224 | 0 | 0.147 | 18.3 / 31.5 | 1270 / 4270 | 6.6 | game_20261118_175107 |
| unit-barb-v1a | barb-easy-2 | cap | 20.0 | 144 | answered_until_stopped | 2176 | 0.890 | 239 | 0 | 0.063 | 17.6 / 29.9 | 706 / 1963 | 11.2 | game_20261118_175255 |
| unit-barb-v1a | barb-easy-3 | loss | 13.8 | 106 | answered_until_stopped | 1680 | 0.965 | 58 | 1 | 0.017 | 16.5 / 25.7 | 1005 / 3751 | 17.5 | game_20261118_175525 |
| unit-v2b-cd90 | simple-1 | loss | 7.4 | 136 | answered_until_stopped | 788 | 0.944 | 44 | 0 | 0.000 | 38.8 / 77.3 | 1032 / 5355 | 8.6 | game_20261118_183240 |
| unit-v2b-cd90 | simple-2 | loss | 6.0 | 95 | answered_until_stopped | 727 | 0.911 | 65 | 1 | 0.154 | 31.3 / 55.6 | 1703 / 5096 | 8.3 | game_20261118_183511 |
| unit-v2b-cd90 | simple-3 | cap | 20.0 | 242 | answered_until_stopped | 1989 | 0.697 | 602 | 1 | 0.462 | 36.4 / 65.5 | 4457 / 6276 | 61.8 | game_20261118_183657 |
| unit-v2b-cd90 | barb-easy-1 | cap | 20.0 | 312 | answered_until_stopped | 1935 | 0.403 | 1155 | 2 | 0.749 | 50.7 / 105.7 | 364 / 4735 | 23.7 | game_20261118_184113 |
| unit-v2b-cd90 | barb-easy-2 | cap | 20.0 | 296 | answered_until_stopped | 2141 | 0.947 | 113 | 0 | 0.088 | 32.2 / 76.4 | 1068 / 4040 | 25.8 | game_20261118_184643 |
| unit-v2b-cd90 | barb-easy-3 | cap | 20.0 | 170 | answered_until_stopped | 2140 | 0.966 | 73 | 4 | 0.068 | 23.4 / 36.3 | 170 / 2279 | 26.5 | game_20261118_185150 |
| unit-v2b-t0.4 | simple-1 | loss | 7.3 | 84 | answered_until_stopped | 1062 | 0.989 | 12 | 0 | 0.083 | 18.3 / 27.1 | 912 / 3434 | 2 | game_20261118_181548 |
| unit-v2b-t0.4 | simple-2 | loss | 5.3 | 71 | answered_until_stopped | 769 | 0.953 | 36 | 0 | 0.056 | 20.2 / 35.7 | 607 / 4671 | 9.6 | game_20261118_181720 |
| unit-v2b-t0.4 | simple-3 | loss | 6.3 | 84 | answered_until_stopped | 867 | 0.956 | 38 | 0 | 0.026 | 22.0 / 43.4 | 1290 / 4551 | 9.0 | game_20261118_181838 |
| unit-v2b-t0.4 | barb-easy-1 | loss | 17.5 | 199 | answered_until_stopped | 1948 | 0.437 | 1097 | 2 | 0.801 | 31.1 / 58.8 | 2822 / 12669 | 14.3 | game_20261118_182010 |
| unit-v2b-t0.4 | barb-easy-2 | cap | 20.0 | 270 | answered_until_stopped | 2106 | 0.181 | 1724 | 0 | 0.789 | 39.1 / 79.3 | 8326 / 9023 | 36.6 | game_20261118_182339 |
| unit-v2b-t0.4 | barb-easy-3 | loss | 13.5 | 154 | answered_until_stopped | 1660 | 0.948 | 86 | 0 | 0.000 | 24.4 / 37.6 | 654 / 5490 | 12.3 | game_20261118_182818 |
| unit-v2b-t0.7 | simple-1 | loss | 8.8 | 117 | answered_until_stopped | 1089 | 0.968 | 35 | 0 | 0.029 | 25.7 / 55.1 | 2172 / 4645 | 11.6 | game_20261118_175945 |
| unit-v2b-t0.7 | simple-2 | cap | 20.0 | 231 | answered_until_stopped | 2177 | 0.748 | 549 | 0 | 0.359 | 28.7 / 54.5 | 7548 / 6099 | 69.4 | game_20261118_180151 |
| unit-v2b-t0.7 | simple-3 | loss | 6.7 | 91 | answered_until_stopped | 929 | 0.978 | 20 | 0 | 0.050 | 21.7 / 32.1 | 428 / 3806 | 11.2 | game_20261118_180552 |
| unit-v2b-t0.7 | barb-easy-1 | loss | 9.8 | 136 | answered_until_stopped | 1241 | 0.809 | 237 | 1 | 0.477 | 26.3 / 53.9 | 1672 / 9540 | 19.7 | game_20261118_180733 |
| unit-v2b-t0.7 | barb-easy-2 | loss | 10.0 | 129 | answered_until_stopped | 1271 | 0.951 | 62 | 2 | 0.065 | 22.8 / 44.0 | 1473 / 5678 | 12.9 | game_20261118_181000 |
| unit-v2b-t0.7 | barb-easy-3 | cap | 20.0 | 198 | answered_until_stopped | 2241 | 0.963 | 82 | 0 | 0.024 | 23.1 / 36.3 | 138 / 1262 | 26.1 | game_20261118_181220 |
| unit-v2b | simple-1 | loss | 11.8 | 181 | answered_until_stopped | 1510 | 0.914 | 130 | 1 | 0.185 | 25.1 / 53.7 | 446 / 7234 | 10.9 | game_20261118_163543 |
| unit-v2b | simple-2 | loss | 12.8 | 132 | policy_timeout | 815 | 0.840 | 130 | 0 | 0.315 | 21.8 / 34.5 | 2384 / 8600 | 12.9 | game_20261118_163855 |
| unit-v2b | simple-3 | cap | 20.0 | 191 | answered_until_stopped | 2280 | 0.991 | 20 | 0 | 0.000 | 20.8 / 35.1 | 0 / 627 | 4.3 | game_20261118_164115 |
| unit-v2b | barb-easy-1 | cap | 20.0 | 197 | answered_until_stopped | 2297 | 0.979 | 48 | 0 | 0.021 | 20.1 / 37.1 | 277 / 2199 | 13.0 | game_20261118_164434 |
| unit-v2b | barb-easy-2 | cap | 20.0 | 153 | policy_timeout | 892 | 0.849 | 135 | 0 | 0.304 | 19.5 / 35.7 | 138 / 1239 | 30.0 | game_20261118_164759 |
| unit-v2b | barb-easy-3 | loss | 6.2 | 72 | answered_until_stopped | 882 | 0.968 | 28 | 0 | 0.000 | 18.3 / 26.6 | 692 / 4073 | 6.1 | game_20261118_165039 |

## Per policy and opponent

Cells with three numbers are: mean (lowest to highest) over the episodes.

Win rate = games won / games played; a game that reached the cap without a winner is not a win.

| Policy | Opponent | Episodes | Win rate | Win / loss / cap | Policy stopped early | Game min | No-order share | Orders without engine callback | p95 ms |
|---|---|---|---|---|---|---|---|---|---|
| builtin-barb | simple | 3 | 1 of 3 | 1 / 0 / 2 | 0 | 17.5 (12.4 to 20.0) | - | - | - |
| builtin-barb | barb-easy | 3 | 1 of 3 | 1 / 0 / 2 | 0 | 17.8 (13.4 to 20.0) | - | - | - |
| scripted | simple | 3 | 0 of 3 | 0 / 3 / 0 | 3 | 5.3 (5.0 to 5.6) | 0.996 (0.996 to 0.996) | 0.000 (0.000 to 0.000) | 26.8 (24.7 to 30.3) |
| scripted | barb-easy | 3 | 0 of 3 | 0 / 1 / 2 | 1 | 18.9 (16.7 to 20.0) | 0.999 (0.999 to 0.999) | 0.000 (0.000 to 0.000) | 28.7 (26.4 to 30.2) |
| standin-human-v1 | simple | 3 | 0 of 3 | 0 / 0 / 3 | 0 | 20.0 (20.0 to 20.0) | 0.000 (0.000 to 0.000) | 0.796 (0.785 to 0.813) | 51.3 (43.8 to 61.0) |
| standin-human-v1 | barb-easy | 3 | 0 of 3 | 0 / 0 / 3 | 1 | 20.0 (20.0 to 20.0) | 0.000 (0.000 to 0.000) | 0.825 (0.802 to 0.837) | 57.2 (51.2 to 63.8) |
| unit-barb-v1a | simple | 3 | 0 of 3 | 0 / 2 / 1 | 1 | 11.7 (6.1 to 20.0) | 0.601 (0.000 to 0.919) | 0.008 (0.000 to 0.017) | 48.1 (23.7 to 89.3) |
| unit-barb-v1a | barb-easy | 3 | 0 of 3 | 0 / 2 / 1 | 0 | 15.0 (11.2 to 20.0) | 0.899 (0.841 to 0.965) | 0.076 (0.017 to 0.147) | 29.0 (25.7 to 31.5) |
| unit-v2b-cd90 | simple | 3 | 0 of 3 | 0 / 2 / 1 | 0 | 11.1 (6.0 to 20.0) | 0.851 (0.697 to 0.944) | 0.205 (0.000 to 0.462) | 66.1 (55.6 to 77.3) |
| unit-v2b-cd90 | barb-easy | 3 | 0 of 3 | 0 / 0 / 3 | 0 | 20.0 (20.0 to 20.0) | 0.772 (0.403 to 0.966) | 0.302 (0.068 to 0.749) | 72.8 (36.3 to 105.7) |
| unit-v2b-t0.4 | simple | 3 | 0 of 3 | 0 / 3 / 0 | 0 | 6.3 (5.3 to 7.3) | 0.966 (0.953 to 0.989) | 0.055 (0.026 to 0.083) | 35.4 (27.1 to 43.4) |
| unit-v2b-t0.4 | barb-easy | 3 | 0 of 3 | 0 / 2 / 1 | 0 | 17.0 (13.5 to 20.0) | 0.522 (0.181 to 0.948) | 0.530 (0.000 to 0.801) | 58.6 (37.6 to 79.3) |
| unit-v2b-t0.7 | simple | 3 | 0 of 3 | 0 / 2 / 1 | 0 | 11.8 (6.7 to 20.0) | 0.898 (0.748 to 0.978) | 0.146 (0.029 to 0.359) | 47.2 (32.1 to 55.1) |
| unit-v2b-t0.7 | barb-easy | 3 | 0 of 3 | 0 / 2 / 1 | 0 | 13.3 (9.8 to 20.0) | 0.908 (0.809 to 0.963) | 0.189 (0.024 to 0.477) | 44.7 (36.3 to 53.9) |
| unit-v2b | simple | 3 | 0 of 3 | 0 / 2 / 1 | 1 | 14.9 (11.8 to 20.0) | 0.915 (0.840 to 0.991) | 0.167 (0.000 to 0.315) | 41.1 (34.5 to 53.7) |
| unit-v2b | barb-easy | 3 | 0 of 3 | 0 / 1 / 2 | 1 | 15.4 (6.2 to 20.0) | 0.932 (0.849 to 0.979) | 0.108 (0.000 to 0.304) | 33.1 (26.6 to 37.1) |

## Time

- Episodes played: 48 (runner errors: 0).
- Wall time per game, engine start to exit: 151 (57 to 312) seconds.
- One game at a time: 23.9 games per hour (120.7 minutes for 48 games; the server start and the image check before each game are not in this time).
- Game time played: 708 minutes.
