# Lane-tag fixture graph

lane_tags.osm is the graph used by test_osm_xml_lane_tags. It is generated
from CASES in tests/test_network_lane_tags.py, one way per case way.

Regenerate both files after editing CASES:

    PYTHONPATH=src python tests/test_network_lane_tags.py --write-fixture

Way id is 1000 + flat index; its nodes are 2 * flat index + 1 and
2 * flat index + 2, so no two ways share geometry. Load it with
ox.settings.useful_tags_way extended by REQUIRED_WAY_TAGS, then
ox.graph.graph_from_xml(path, bidirectional=False, simplify=False, retain_all=True).

| Way | Case | Reference | Tags | + | - |
|---|---|---|---|---|---|
| 1000 | L1a-1 | L1a, cycleway=lane | highway=secondary, cycleway=lane | True | True |
| 1001 | L1a-2 | L1a, cycleway:left=lane + cycleway:right=lane | highway=secondary, cycleway:left=lane, cycleway:right=lane | True | True |
| 1002 | L1a-3 | L1a, cycleway:both=lane | highway=secondary, cycleway:both=lane | True | True |
| 1003 | L1b-1 | L1b, cycleway:right=lane + cycleway:right:oneway=no | highway=secondary, cycleway:right=lane, cycleway:right:oneway=no | True | True |
| 1004 | L1b-2 | L1b, cycleway=lane (indistinguishable from L1a) | highway=secondary, cycleway=lane | True | True |
| 1005 | L2 | L2, cycleway:right=lane | highway=secondary, cycleway:right=lane | True | False |
| 1006 | M1-1 | M1, oneway=yes + cycleway=lane + oneway:bicycle=no | highway=secondary, oneway=yes, cycleway=lane, oneway:bicycle=no | True | True |
| 1007 | M1-2 | M1, oneway=yes + side lanes + oneway:bicycle=no | highway=secondary, oneway=yes, cycleway:left=lane, cycleway:right=lane, oneway:bicycle=no | True | True |
| 1008 | M2a-1 | M2a, oneway=yes + cycleway:right=lane | highway=secondary, oneway=yes, cycleway:right=lane | True | absent |
| 1009 | M2a-2 | M2a, oneway=yes + cycleway=lane | highway=secondary, oneway=yes, cycleway=lane | True | absent |
| 1010 | M2b-1 | M2b, oneway=yes + cycleway:left=lane | highway=secondary, oneway=yes, cycleway:left=lane | True | absent |
| 1011 | M2b-2 | M2b, oneway=yes + cycleway=lane | highway=secondary, oneway=yes, cycleway=lane | True | absent |
| 1012 | M2c | M2c, oneway=yes + lanes=2 + cycleway=lane | highway=secondary, oneway=yes, lanes=2, cycleway=lane | True | absent |
| 1013 | M2d | M2d, bidirectional left lane | highway=secondary, oneway=yes, oneway:bicycle=no, cycleway:left=lane, cycleway:left:oneway=no | True | True |
| 1014 | M3a | M3a, contraflow left lane | highway=secondary, oneway=yes, oneway:bicycle=no, cycleway:left=lane, cycleway:left:oneway=-1 | False | True |
| 1015 | M3b | M3b, contraflow right lane | highway=secondary, oneway=yes, oneway:bicycle=no, cycleway:right=lane, cycleway:right:oneway=-1 | False | True |
| 1016 | M4-1 | M4, two one-way carriageways, each as M2a | highway=secondary, oneway=yes, cycleway:right=lane | True | absent |
| 1017 | M4-1 | M4, two one-way carriageways, each as M2a | highway=secondary, oneway=yes, cycleway:right=lane | True | absent |
| 1018 | M4-2 | M4, alternative single way as L1a | highway=secondary, cycleway=lane | True | True |
| 1019 | M5-1 | M5, Way A as M2a, Way B oneway=yes | highway=secondary, oneway=yes, cycleway:right=lane | True | absent |
| 1020 | M5-1 | M5, Way A as M2a, Way B oneway=yes | highway=secondary, oneway=yes | False | absent |
| 1021 | M5-2 | M5, alternative Way A as L2 | highway=secondary, cycleway:right=lane | True | False |
| 1022 | T1-1 | T1, road with use_sidepath and two one-way cycleways | highway=secondary, bicycle=use_sidepath | False | False |
| 1023 | T1-1 | T1, road with use_sidepath and two one-way cycleways | highway=cycleway, oneway=yes | True | absent |
| 1024 | T1-1 | T1, road with use_sidepath and two one-way cycleways | highway=cycleway, oneway=yes | True | absent |
| 1025 | T1-2 | T1, alternative single way cycleway=track | highway=secondary, cycleway=track | True | True |
| 1026 | T2-1 | T2, road with use_sidepath and a two-way cycleway | highway=secondary, bicycle=use_sidepath | False | False |
| 1027 | T2-1 | T2, road with use_sidepath and a two-way cycleway | highway=cycleway, oneway=no | True | True |
| 1028 | T2-2 | T2, alternative cycleway:right=track + :oneway=no | highway=secondary, cycleway:right=track, cycleway:right:oneway=no | True | True |
| 1029 | T3-1 | T3, one-way road with use_sidepath and a two-way cycleway | highway=secondary, oneway=yes, bicycle=use_sidepath | False | absent |
| 1030 | T3-1 | T3, one-way road with use_sidepath and a two-way cycleway | highway=cycleway, oneway=no | True | True |
| 1031 | T3-2 | T3, alternative one-way road + cycleway:right=track | highway=secondary, oneway=yes, oneway:bicycle=no, cycleway:right=track | True | True |
| 1032 | T4-1 | T4, bicycle:forward=use_sidepath and a one-way cycleway | highway=secondary, bicycle:forward=use_sidepath | False | False |
| 1033 | T4-1 | T4, bicycle:forward=use_sidepath and a one-way cycleway | highway=cycleway, oneway=yes | True | absent |
| 1034 | T4-2 | T4, alternative cycleway:right=track | highway=secondary, cycleway:right=track | True | False |
| 1035 | S1 | S1, oneway=yes + oneway:bicycle=no without a lane | highway=secondary, oneway=yes, oneway:bicycle=no | False | False |
| 1036 | S2-1 | S2, right lane with bicycle:backward=use_sidepath, plus a cycleway | highway=secondary, cycleway:right=lane, bicycle:backward=use_sidepath | True | False |
| 1037 | S2-1 | S2, right lane with bicycle:backward=use_sidepath, plus a cycleway | highway=cycleway, oneway=yes | True | absent |
| 1038 | S2-2 | S2, alternative cycleway:left=track + cycleway:right=lane | highway=secondary, cycleway:left=track, cycleway:right=lane | True | True |
| 1039 | S3-1 | S3, cycleway=track + segregated=yes | highway=secondary, cycleway=track, segregated=yes | True | True |
| 1040 | S3-2 | S3, separate sidewalk ways, cycleway ways | highway=secondary, bicycle=use_sidepath | False | False |
| 1041 | S3-2 | S3, separate sidewalk ways, cycleway ways | highway=cycleway, oneway=yes | True | absent |
| 1042 | S3-2 | S3, separate sidewalk ways, cycleway ways | highway=cycleway, oneway=yes | True | absent |
| 1043 | S3-3 | S3, separate path ways with bicycle=designated | highway=secondary, bicycle=use_sidepath | False | False |
| 1044 | S3-3 | S3, separate path ways with bicycle=designated | highway=path, bicycle=designated, oneway=yes, foot=designated, segregated=yes | True | absent |
| 1045 | S3-3 | S3, separate path ways with bicycle=designated | highway=path, bicycle=designated, oneway=yes, foot=designated, segregated=yes | True | absent |
| 1046 | S3-4 | S3, separate cycleway ways with foot=designated | highway=secondary, bicycle=use_sidepath | False | False |
| 1047 | S3-4 | S3, separate cycleway ways with foot=designated | highway=cycleway, oneway=yes, foot=designated, segregated=yes | True | absent |
| 1048 | S3-4 | S3, separate cycleway ways with foot=designated | highway=cycleway, oneway=yes, foot=designated, segregated=yes | True | absent |
| 1049 | S4-1 | S4, easiest: cycleway=track + segregated + foot=designated | highway=secondary, cycleway=track, segregated=yes, foot=designated | True | True |
| 1050 | S4-2 | S4, separate cycleway ways with foot=designated | highway=secondary, bicycle=use_sidepath | False | False |
| 1051 | S4-2 | S4, separate cycleway ways with foot=designated | highway=cycleway, oneway=yes, foot=designated, segregated=yes | True | absent |
| 1052 | S4-2 | S4, separate cycleway ways with foot=designated | highway=cycleway, oneway=yes, foot=designated, segregated=yes | True | absent |
| 1053 | S4-3 | S4, five-way variant with separate footways | highway=secondary, bicycle=use_sidepath | False | False |
| 1054 | S4-3 | S4, five-way variant with separate footways | highway=cycleway, oneway=yes | True | absent |
| 1055 | S4-3 | S4, five-way variant with separate footways | highway=footway | False | False |
| 1056 | S4-3 | S4, five-way variant with separate footways | highway=cycleway, oneway=yes | True | absent |
| 1057 | S4-3 | S4, five-way variant with separate footways | highway=footway | False | False |
| 1058 | S5-1 | S5, shared path with bicycle=designated | highway=path, segregated=yes, foot=designated, bicycle=designated, surface=paved | True | True |
| 1059 | S5-2 | S5, separate footway and cycleway | highway=footway, surface=paving_stones | False | False |
| 1060 | S5-2 | S5, separate footway and cycleway | highway=cycleway, surface=asphalt | True | True |
| 1061 | S6 | S6, steps with a bicycle ramp | highway=steps, ramp:bicycle=yes, ramp:stroller=yes, ramp:wheelchair=no | False | False |
| 1062 | S7-footway | S7, highway=footway + bicycle=designated + segregated=no | highway=footway, bicycle=designated, foot=designated, segregated=no, surface=paved | True | True |
| 1063 | S7-cycleway | S7, highway=cycleway + bicycle=designated + segregated=no | highway=cycleway, bicycle=designated, foot=designated, segregated=no, surface=paved | True | True |
| 1064 | S7-path | S7, highway=path + bicycle=designated + segregated=no | highway=path, bicycle=designated, foot=designated, segregated=no, surface=paved | True | True |
| 1065 | S8 | S8, highway=footway + bicycle=yes | highway=footway, bicycle=yes | False | False |
| 1066 | B1 | B1, lanes layout with bicycle:lanes=designated on both sides | highway=secondary, lanes=3, lanes:forward=2, access:lanes=no\|yes\|yes\|no\|no, bicycle:lanes=designated\|yes\|yes\|designated\|yes, bus:lanes=no\|yes\|yes\|no\|designated, taxi:lanes=no\|yes\|yes\|no\|designated | True | True |
| 1067 | B2 | B2, bus lane right plus cycleway=lane | highway=secondary, lanes=3, lanes:forward=2, lanes:bus:forward=1, busway:right=lane, cycleway=lane | True | True |
| 1068 | B3 | B3, left lane plus shared busway on the right | highway=secondary, busway:right=lane, cycleway:left=lane, cycleway:right=share_busway | False | True |
| 1069 | B4-1 | B4, bus way with shared busway, road one-way for bicycles | highway=service, service=bus, oneway=yes, cycleway:right=share_busway | False | absent |
| 1070 | B4-1 | B4, bus way with shared busway, road one-way for bicycles | highway=secondary, oneway:bus=yes, oneway:bicycle=yes | False | False |
| 1071 | B4-2 | B4, bus way with shared busway, road two-way for bicycles | highway=service, service=bus, oneway=yes, cycleway:right=share_busway | False | absent |
| 1072 | B4-2 | B4, bus way with shared busway, road two-way for bicycles | highway=secondary | False | False |
| 1073 | B5 | B5, shared busway on the right | highway=secondary, lanes=4, lanes:bus:forward=1, busway:right=lane, cycleway:right=share_busway | False | False |
| 1074 | B6-1 | B6, contraflow shared busway, busway=opposite_lane | highway=secondary, oneway=yes, oneway:bicycle=no, cycleway:left=share_busway, cycleway:left:oneway=-1, busway=opposite_lane | False | False |
| 1075 | B6-2 | B6, contraflow shared busway, busway=lane | highway=secondary, oneway=yes, oneway:bus=no, oneway:bicycle=no, cycleway:left=share_busway, cycleway:left:oneway=-1, busway=lane | False | False |
| 1076 | M3a-no-onewaybicycle | M3a tagging without oneway:bicycle=no | highway=secondary, oneway=yes, cycleway:left=lane, cycleway:left:oneway=-1 | False | True |
| 1077 | M3b-no-onewaybicycle | M3b tagging without oneway:bicycle=no | highway=secondary, oneway=yes, cycleway:right=lane, cycleway:right:oneway=-1 | False | True |
| 1078 | LEG-opposite-lane | legacy cycleway=opposite_lane | highway=secondary, oneway=yes, cycleway=opposite_lane | False | True |
| 1079 | LEG-opposite-track-left | legacy cycleway:left=opposite_track | highway=secondary, oneway=yes, cycleway:left=opposite_track | False | True |
| 1080 | LEG-opposite | legacy cycleway=opposite, contraflow without a lane | highway=secondary, oneway=yes, cycleway=opposite | False | False |
| 1081 | cyclestreet | cycle street, shared carriageway | highway=secondary, cyclestreet=yes | False | False |
| 1082 | bicycle-road | bicycle road, cars may be allowed by sign | highway=secondary, bicycle_road=yes | False | False |
| 1083 | pedestrian-street | highway=pedestrian + bicycle=yes | highway=pedestrian, bicycle=yes | False | False |
| 1084 | path-plain | off-road highway=path without bicycle=designated | highway=path | False | False |
| 1085 | track-plain | off-road highway=track | highway=track | False | False |
| 1086 | track-designated | highway=track + bicycle=designated | highway=track, bicycle=designated | False | False |
| 1087 | bicycle-use_sidepath | bicycle=use_sidepath alone | highway=secondary, bicycle=use_sidepath | False | False |
| 1088 | bicycle-optional_sidepath | bicycle=optional_sidepath alone | highway=secondary, bicycle=optional_sidepath | False | False |
| 1089 | bicycle-dismount | bicycle=dismount alone | highway=secondary, bicycle=dismount | False | False |
| 1090 | bicycle-permissive | bicycle=permissive alone | highway=secondary, bicycle=permissive | False | False |
| 1091 | bicycle-destination | bicycle=destination alone | highway=secondary, bicycle=destination | False | False |
| 1092 | bicycle-yes | bicycle=yes alone | highway=secondary, bicycle=yes | False | False |
| 1093 | bicycle-designated-road | bicycle=designated on a road without a lane | highway=secondary, bicycle=designated | False | False |
| 1094 | advisory-right | cycleway:right=lane with an advisory lane | highway=secondary, cycleway:right=lane, cycleway:right:lane=advisory | True | False |
| 1095 | advisory-both | cycleway:both=lane with an advisory lane | highway=secondary, cycleway:both=lane, cycleway:both:lane=advisory | True | True |
| 1096 | shared-cycleway | highway=cycleway + foot=designated + segregated=no | highway=cycleway, foot=designated, segregated=no | True | True |
| 1097 | shared-footway | highway=footway + bicycle=designated + segregated=no | highway=footway, bicycle=designated, segregated=no | True | True |
