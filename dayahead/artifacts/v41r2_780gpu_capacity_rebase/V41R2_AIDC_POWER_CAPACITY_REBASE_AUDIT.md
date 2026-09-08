# V41R2 AIDC power capacity rebase

V35R3J derives c_ref in W per requested GPU from the historical aggregate/624. V39A explicitly freezes c_ref and CENTER and decomposes installed idle plus active swing. V41R2 retains those per-GPU values; its enlarged aggregate is derived.

Frozen per GPU: c_ref=651.884605470864 W; CENTER=547.7239090195797 W; equivalent idle=104.1606964512843 W.

Full active aggregate: 406.775993813819136 → 508.46999226727392 kW. Installed idle: 64.9962745856014032 → 81.245343232001754 kW.

The legacy fixed-624 aggregate formula is invalid for 780 and is replaced with the sum of installed idle and active swing. C1, weather, PF and site hosts are frozen. Conservation passes at 2E-12 kW tolerance. These are synthetic equivalent-GPU powers, with no measured-facility claim.
