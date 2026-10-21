"""No repository an Agent host can check out holds the chief exam's grading keys (TD-396).

    python3 -m pytest -q scripts/agentrt/test_no_exam_keys.py

The chief of staff's qualifying exam (W-31 2.4; CUT-chief-exam-2026-10-19.md) is graded by
rules kept out of every repository: agentd on the Agent host checks infra out (since 10-19) and
every repository is public on GitHub, so keys here are keys the examinee, or anyone, can read,
and the exam would measure recall instead of judgement. They live on the Owner's Mac beside the
set (~/agent-work/chief-exam-2026-10-19/) and, for grading, in the platform's exam Secret.

What this refuses, over every tracked file whatever its name or extension (a regression check
of the shapes keys have leaked in or would, not a proof that no key is here; a paraphrase in
prose still needs a reader):
  - a rule id of the set, also inside a longer hyphenated word;
  - a regular expression a rule matches with (10 characters or more), pasted as a double- or
    single-quoted or backticked string or alone on a line, raw or as JSON escapes it (a raw
    pattern that holds a line break, or the quote or backtick it is wrapped in, is found only
    JSON-escaped);
  - the shape of the set's files: a rule object (its kind is one of the grader's; alert and
    card, ordinary words, only with a key of their own rules), a question of the chief's exam,
    an answer kept as a control of a sub-question;
  - three or more rows or list items that start with a sub-question (Q3a), the cut's old §10;
  - a file of the set by its name (q<n>-<name>.json, controls.json, grade_reference.py).
The ids and patterns are kept here only as sha256 fingerprints, made by keyhashes.py beside
the set (python3 -I ~/agent-work/chief-exam-2026-10-19/keyhashes.py, after the set changes).
A fingerprint recognizes a key; it is no secret store: an id or pattern someone guesses can be
checked against it.

The pre-commit hook (agent-config/scripts/git-hooks/pre-commit) runs the same checks over the
staged copies of what a commit stages: python3 -I scripts/agentrt/test_no_exam_keys.py --staged.
"""
from __future__ import annotations

import collections
import hashlib
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULE_ID_SHA256 = {
    "1168ce8d46f362de398e9932d3bc95cfaee2a54d5083da48e3211a503a7355db",
    "14624f2ec2a5390e862eadcca1699c6e5e2dc0d8a3efe2b65210a53d51f63187",
    "313101751b93a3ae6e21fa1f9aaef890fce667934fe04e53e822a50beaf84484",
    "33bffa7fb5db286de0d1c39bd180ad28a1c6183ffc3326f9c0b08f488db28977",
    "60190d8b60dc300784905e06ffc5e07e915cc97726046d03955d45cea6b87705",
    "6967d9e8c29c1ff956bb28f663f8dd6bdec9a29d85b49eecd14fe0939fdea83d",
    "71aa7947444de601d88ad5231d8d6e24c6dd10d46ba53d035911d20ef3a945b4",
    "7519f503bb8e987e0ff0246fe15db9618464bfe902bcf802f997231c99d60ded",
    "775ec12f795e3b8937dc90f933217e007a024bd2d3bb9cc59b305a87721bcacb",
    "999a4c403ee8171a7976838dce7206a42aeb0daffa3545b0b45c3d613764645b",
    "9e589e859b53a2ba6c2291a3bd675f1f11ecd59a97f9e7d05d51fc6635b6969d",
    "aae503232c2638c4fba48e83ba6112bbdc72c7ed79a06626ae1fef53f8d3a47b",
    "ad44f983fd97e56483410ffcea97d6989f64772ff192cb469a12ffffcaa37776",
    "b01980bba922151d93e582030c85004d1913699039422fb37c64a4d86991ce7e",
    "b4a1510ee29ef9710d6170e25294a5dc12c1b25b5539ffb74adca4bf5d284b26",
    "b9f0f3598dda85e05ce45fe7df0ca7421c2210d1de8459402f6925b54471fba6",
    "bbcd0965dee081d1f37125806565ef39bb778bb8d06f47ad712309fc850bf691",
    "bd60ec61be6a111f955ba44a85e44e0be5c9365940ab1b539bd718f63b2120e6",
    "bd77bcd73ef6a04c7380c97303b2e147974931cea8e65b39b27bbfa75ba4089e",
    "bf65c344dd70f8276d78ca64c7d4a987d6f7d2a7eca8aa6022fc862b9c2a820d",
    "bfe8474b9351154561c73cb8401bacfd9498e52a2d9df337b4e9d045c86746a1",
    "c06c2b3568f20decd600cde9de74aa3bc0cd8e64d2107b31104197d2d9b5f75a",
    "d15f8d4eac4d7c3a835da05c5ce4059c2ac9d675ec2c46258f88d6c508052710",
    "d25931b9a27426b193439fd1fb769866d986cacd1234c2e7578a8ab9f56a14b3",
    "d2946c470a22c3267c6e250b668ccb378a20dc28375a7ab8fa121009c1e0b711",
    "d60acf00e6858b65dadfb273c3395d9cfc8ee80a8be3efe4bb7451f7c64505f5",
    "d94d2290744f94efb2e9344c8545bf1401171355fb318dfdc3e7f1ef549339cb",
    "d9d315bd6bfb072fc104dfc73e2590bdfdd453952172da23e376f315e46db161",
    "e8f811173ddb303c183d8880b80789d77e107d02a98f5dfcf8f4b90c07a16a2e",
    "ef819fa902318de15882448d1cc653e1bbd9a227ff98482576d54897b32db2fb",
}
PATTERN_SHA256 = {
    "00f8ba5c4d69c8f526b2a68eb6f530678eb2bbc04a5b46f337cd182044112f89",
    "038867df15d7a324bb5868c11ef778699c3c09619029201c63088c9e8f2cbc79",
    "03a2fd1568adaff512df208f3039286d10e6f1a83cf7fb4e2685a5dc85ce82a8",
    "07b6357c3d4ad554b31d2ba5e000883bb9aa0636bbed651130d49cec1a510f9e",
    "08040a969bbda8b64dd7eac64fd6745d932590c1bfa7d7eea8fc26e9d09574d5",
    "08fae9697678adbb3d4aeaacc471f6f2932f1642be0e3e83e66e77ddb8e0c516",
    "096e931287af1ab5fd8856dbc92506cd3bb3992e12ca5e783badff3844714475",
    "0b0ba26bf3c9169aba8cb741a6db4ff2cf00186b59a388f61c1774ea4fcee4da",
    "0f1a6fca1f3e083b98283aedb57628d0e05278fc1048a6efa15a92d3713caf5b",
    "0f393ab1df0895b95ea3f11cd7dcb040e3be14aaa6b5c13f360fd4e02edb9378",
    "11a50d1a537e5ad403fe7a60bcfa2ef14e29b50973d1f5fa7b10aa58b4bdb4b5",
    "125df503d8301a7a4b6a6eafdc0e17d660a3cf8867f4b0c8d919d57408b7cc7e",
    "131c1009c6232f7a5093f4815609ed403bc098da1c8b05bcb5b64533b63a49ac",
    "1320dbe4bd576a6c962763b1a9cdbebb4b8910f36e53d61d87f9663d9f9a08c3",
    "14b5ea42eb9e2d30787b817181df64ae39448bc09462acba740bb8e1e975dcae",
    "14e9b0238777fab648b1727e8b5ed59ffa546b438a6120c682e3737da89e7c54",
    "16519db4e5a9b598642cfd0127d28c1a7a112bb8872ddc5cabcef530fdbf8d14",
    "170532e0ba2577517cc0eba6a5dba4d1821bdbc089124064ddf9bedeb8d67733",
    "19956cb60db214391786c86df31edd10ee7f8ffc6b06cfbff8b26e1885a24b8d",
    "1a8588c61580a14363ba3eea0291ffc7b3979f8c48c4f57fa8259a85b7a6df80",
    "1ae6ee93b37ab0e6be220d9b54a776248f85f70f0f25999b9cac9fe30ccf5418",
    "1ddd7584a4d628d348625c930d8953884e932afdb20629bd88989371b89354e8",
    "1f373ee3805023c4627cdb5de3716442430d566ae3e5a8461faf72a6cc41d8a5",
    "21f4efb393068f748c4cb81427681519e0e40acfc6adc881c4fd30bdbe72fc0d",
    "21fa6f9876edba8d922b8ed756b35352fe8c12f84ea9eb342baef4f573618287",
    "21fb1c41e1d14f14a986c19aa995797aea104547e4b6075927b1042c3d484e7d",
    "22adc544bfdbc0d579b007e12a00f426da34003a34f071c966b8805d830a2ef0",
    "23ffce4c4114972d6e99a55ae5bbd8efd0dd69a581003d4d429478eba46218f7",
    "251225194738bb41815d9bb276a29a5c1a074add5f64775e01f322df68585654",
    "25a28ceb40f1507ead79e7a9d95e5b90bdf04e4d625396df4cb4411d319c583f",
    "293dcc9b941ffd09aabbe6c4a10fe21691a9a0eb396dbed93419b10f90973f15",
    "2d28dc01322d7089cfce695b44b302b19c16d4d7af3b8772bed779308dde3b48",
    "2d94414fbe734ae2fc31acb2370d33e816f063b6d013b0799637a98e07eefcc3",
    "2e7e79930ef80b4e1be2556a32e2e4d6292bd0eed7c4f90ca67ef49eb86149dd",
    "2ee4dffbe46df466f13b4810b816bafecd540186c849b9ef86ca0df279a25744",
    "2f2a58bbbfb228113cd278d7be12022a4fe1bd60fa4cbec8c3aaac9340dc2157",
    "3105f9e60f2ff2320bd235b87d18474e7daa29d62a00c2134d504e48d543ca4f",
    "312c3efa9a8996b6363859faafa0a142cb5267dea3ad75f6e54557271f95d330",
    "31adfdcd869b2a005d8afaa4e492750a3f6e7ad8314e9ffcc33e5f3d98cbf857",
    "32cd06c66db511c605985202ae5fa37850f2dfa616842685dae8a7faff41847f",
    "343fa29b05847b79e8620eae575b60cadd59126062e6a6474043a507f2962257",
    "35d28e2bf95d79ce83bd3a68ffea1aee7aad5e8f0390c8951c87805673d6c2de",
    "3636b0973ef24060332cdd6c263c234bb5cebd0874f982b846e6f7b552d6662a",
    "36ee96fb056c55542e6a611ba658e97780746e3f29bfb6b85f8925c4758341d4",
    "370f71a3b217109772a9169d736ffc319432e630fba89d922c1a805504ccd519",
    "375769d01ee83708818330988bd897b6243a5fd52cbfa72df3f514a67a0033a2",
    "39b5b91f0a90296dd1c703e2f734c3f5f556ecc362fc231ebc39f8818506c47d",
    "3b052e3ab66a57c1a1c3ef0c85d3f8dfc9ae914391aad1fd7403b905cf288a3f",
    "3e95313d778e6fba89220a5a8342937ae871af3e2638e67cac528b22a9bbae46",
    "4085c25eaa08651f279cf8960d315be98ef3412a7daf1fa40dcdbdfa493475f6",
    "41dda563b487883b9a48c7f4b5f8a7b5a8279a2e4276abd6e50ba4ee43386f53",
    "42133665d362c47fbbb8657442af1762a00b9f16a26ec1264f17c1be52b89f18",
    "423e35631772eb22c97689aeef59e62bec8ad5a3c88daf778ce0166d2c630729",
    "42cf4eb442a61f5c87186325c98a5fa9311d351c07eb3d852c89b5b1bea36e85",
    "43a8a1b299cf8f07d792510b682ce0d6b34b16aee831643f670f6234d1df9822",
    "44621439014a4304af1913efb9dda5bee87e818da0b430fa93dbba5a6bffbd7d",
    "44777a99ece8884bee302a4d24cb757c9067dbb4b1c4948138f99c98ec3de48d",
    "452c7e40fcb7522576968f9ff3439753e41f277dbe8eebd319e26382773411d1",
    "4610cc9843f9aa4931d63f17648e6fc6a380a994a75089aae862486d8c03a904",
    "475594cd6d79e9c715eca142ce27e4c7b09008ccc57c0e3f251b0804e15eff84",
    "4761e37fb43f04b0c28ad661b56f7ea4afffdacccfd880cf56350906819639ec",
    "47f7fc642b3b1a1bbe1aa6430b6ae5d116608dae9fd1bdec92c72385dab141d5",
    "4823a82c6be29d9352ec776de30230ec93729c463b11ad6813cf3660fd5d532e",
    "483f7ce4ce31d8b7e3a8fdafcf7478a7a5f1f14c929a07cc6e76619484d3eaa8",
    "487d851d3a24a798e218ff50c9121aca21d9750b216a195f5dffad39f495c358",
    "4eb3d02334fe34dda0f2060bbd21ca4eb00be48922f14e8da6697c484a33747b",
    "4f17e120974d046baf1cd6d0c7153249d4c038b4ec1ce89d0aae272b939b02f2",
    "51158316e373fb4689a7fb599ae8d5893f1f15c0596e5dcfc3ce937ae07417d5",
    "549b2f2c63c93e1d9deef8878d5ea7be55e6356fa6023e84203a65f4dd7600c6",
    "5579b003d4f635891318008837f56f3b45f0d67aa6a78f0eb1c9a8d1a5914155",
    "55a1b52508de03247fd1165874fb45dbfa53613f1341f2c4098a73b59e74966e",
    "580c383ce9ef930f6b06aebebcbbdef013e18aabe2de17b7dff7e7072e011e76",
    "58ec484a4f0ef5f4bb028234fb206b33aa24baa0063c89d89b01fae4bcbda8d8",
    "59505d4eb142066493c18e990a2af34309a611b838120075ab6c128394fb3c43",
    "595c30bbfb4f8d2b44810ced8ccb0cc226b8253e45858bddb1c3a03418e33946",
    "59a0af01e378e04d80c880c2e45306829aa372f249222d682f7dbb6fccdeafab",
    "5ac4f06a6c3e0bf0bb613e6223341d691b149db1b7864deba3dcaf9b3ea478a2",
    "5b8a7e2c5180cb5de6153ff00f9eb9e1fd8be242596c526572119e8e2400624e",
    "5c94efa88c4911e92bf2dfcc42152c69a1f62406991790fb97e45cb1557a3107",
    "5d890c953b1d860a4c9b8c0c188162920baecbed30475dbe079698b16d5ccfce",
    "5e8a90458c305754a6597862d78851d23f13fe9cbe2932543c5a6b23ae546468",
    "5ebb1a8ed01280255df122155965a87c8aef80b71b6a1e855a045e33c104f7eb",
    "5ef81c86c6fbd82e10ac6bece3cddfbdba0dffb47960acf0c8e3f4094c1d9e90",
    "5f720502196b45aba77b1036e6dc055d76caaef81040065bcdd31a3ddbf7c3a3",
    "6067d4c8e8a18cf5aeb9f25f1f084c9d51c88f2769b83e5c48f2177427aa4380",
    "60828c0f47cb22d18f214649d0e08860ad6552aaba5351c9c92b1983874a9d25",
    "61029c99a2a142942df0d532a7e49ce76d60ebabcc3665564bc8510e5ea87622",
    "6227aeba4dcaaba29f1aae6f93fd9ee5ac2097650c1950bb31151aacfb860a47",
    "626f8b9b0eb1c0f38a417fe1b6974ce9a232a4edcab436d6c03352ec7952ab6b",
    "649741de7d81ee9e5ddb4b8ffcb57bd14005acfe22ccbec001d278776f35efea",
    "652fd7f1c0eca9c8413d1c46097508000fa5027d96f320abfe66f67ff8ac4c17",
    "66a68113870f506cb2efa436e5ac5cc9e5e3a602bd3ea9064387260ef89df020",
    "6747830feccba570d1cf00e2114e2ff741b5b3049c2b36cc8b4e5a4bdbd06065",
    "68122e248ef656724a1282a0236928274b293c29802c22ec8adedfad2a0af3e5",
    "685585eac14ce7b7c79dfe2b5663e8dff87cdcf608cde97248b25f73ee7070e6",
    "6859be0b74ed1359abe83d44c3f950c1a93c7b0b434bbc97f72ce80f747ef427",
    "6a0514eeae57f74f1e0645d96d8461c29a34be167d11eb64df1d562e28f36b76",
    "6db7e51b65d8595bc40d45b0163b095faa81c5a8eee9a67e811cd62b4bf8240d",
    "70fdb7ed7ab47b6abf4f15bc20e5fb3cd35e3c2349985393e54ff048d5f15a53",
    "71d2273ab1f7fe5af398e09156177ed2a41bae200eb99a6afa5a6d3746772a97",
    "723b66d42b1180a82019a6505f14682e307fa18269a14058d4861330d6b756ab",
    "72d5338c41f2e88300069245483a8e876f983a3cb09dbaacee82513ac3e9a1b3",
    "73c2e6a6899833ca03384372d2299afc69b6e5acd628e12249103090c027d574",
    "74275ccf63d732702a31f0bc9325b3e862141a35d7ef223e83dc2c635a2292dd",
    "768e9ffe04f4da965ada95f0c97f56978542988ded96d80d6e59cb8ddb892093",
    "7913a926cb2722cb026bdeb35a0a3a106ed7256fe5fb21edc259065f82ea4a14",
    "7a3ee961a8e93951fef354c97c5ef2cd00337864e6f874834bbc3536b16dbcd0",
    "7a541299d204fd6b23c9e3f56838dd572331c96e672bdef02612dc1b7b695808",
    "839fbf5e79e01af8cc3bfa82bb3e9f3959b2203deaa8dcfeb77d29e8afc80fd7",
    "846216e9d553a51ee2f4a9fa60cf6ef509a1d4664cf6a619dbd5656a2897ad62",
    "86967b643e879e9067a7e7421147d3c90b66e5b66569146e7dcd86c866990329",
    "86d626fc20fc79fafebaae951c8582c7e430e5ae24e37010e30eea4b3099d63a",
    "873942dfb1cbcec71c1270386d01b337021744b01f21dd14e7fdf934f0550bd9",
    "87e4385f207a448ab8392176ab961799bfe90c2182566fffd0ef2e0efee2c114",
    "890bb64ff2307426bfcd245b54851c21870efe2e49ebf3ffed75e2aa51a6875a",
    "89ed4542a6268e08f8e973603febec34020e86a676885ff34d9af2dd51c54efb",
    "8a9fbae160af182683f06c72c7fefbc9f2d408458475ccb894dc2869e0be0688",
    "9064bf5dfc53375120c58535dab204db3bfded58e361fb0d380a7e63af8759d2",
    "90b7563beb34e6a010527c475ae2d60fa4ac3da69849741cdf45ba010ed1918c",
    "90fedfb6970b7decda376a9b735862ed6fa2242d31f99500a2b075ec745cbf7d",
    "934a64951d787d862914fd560b62bd04b00114dc3f56d099c47055d9309a859c",
    "93d402732fccae172ac9f9af845d412c162f6b0aba3e9e106e0f9b9d6719a97f",
    "94dd7db9ac73535ae73b5495fe644e21ee6d616cd48756c5665e35c744198c42",
    "95cf5495aaa710e20dc46c112c866225d72ef0771547a2ece782a62ebd3920e7",
    "9667a198dec01fcf625677d206f5433b7d6c0ea3af692e4ef4d6af95365f64b1",
    "968f591307bb5b9a751d51aa1fe80bad9d5a73093b65948afa88355afde07b3a",
    "96962c529af48f34a15d5a0e4e662b8bfb59583091ee209ed1746121bc86424b",
    "98e35f49e77d6574ca0eef67240f6034f11d41dc9794ec5ca1fe7b6e7289e50e",
    "9941cfed4218dd8a2312fabcd9acaed42e0d3508767dc6a8bce96fa62181a147",
    "9c05028ea71312d318fdbb26eb17561a99f9f0787d906e05b962ea8c22533be2",
    "9d6ef9eb2590ed9da0f8b789f94b29713991e17913adb7369d501a1647d8989f",
    "9e3e9b44f8b878bcaca15be04eae3c3b60bb30c6838082f206f4e5650122695d",
    "9efa68b47a049d4d628135f7c4d3c79ed577f75986c9777cfe8dae8f13964afd",
    "a033c1c98782468bd68ebfda176d367f7639c54167057f43a054f7dbb69bf830",
    "a1258f15fddd5fc0568370ca86a5bba2dfff035790af64402d45a83cf9c00129",
    "a169a5a75c115881b96b5ad0471b8eeac748b36f333e992e4b54aa9e964f4238",
    "a1886cdacac9047e56f8819ada657cb390b4d5e0315a3a5bc4e278eb3bf4544b",
    "a1c0774c21c0beaf03d962e8b42801072e94990f0e94a4a6a966e8ead160f40c",
    "a3152a613b99a07d6261a280b40e571b37f517b161e550c9214cb61c350ce688",
    "a40dfb8709dd2286b65ddde16218bf0bd5e035f67e483d3d032116a4387b5cd8",
    "a5ba50a54bb91edae611d38c00de21b9fc3b09fa9c6667c4045f248ec5230a95",
    "a6356424d06c4f8f7c79daa17288fcbbd8ef3f92c13d9622f25d10ecf62bd274",
    "a7d7fbb859989ba66187df8e225a1e8920d556b19b22f48bf44296ae7ddd5273",
    "a7e353e9a3ea34eb2faf8c62f20f263da961f3b3a269c8e1ea10fa3cdae1c91b",
    "aa5956acc98f9e6154838e9069185961d72ce252389a937236fde376b377c057",
    "aa5bfc2c09cc7f8d4be34d705d677ab41f1aa51467a595778e435e8507223a87",
    "b087485c60a0f0566bdb82c78844e41bc873a08f517fd79cab079cce9bd6feac",
    "b15310dca3d74526bcbc5e2a0b504d72bee8e69c0eafce9f8cd84975f6eb685a",
    "b2ead7b75fdfbaddd321e75ca7022bc5d508c05c1f6a293d848d9118c28c4584",
    "b445d7d136a769c086bad59b96c7bae732b59714749c119eaa106ceeaea703ae",
    "b606c31dd4a27f0d7680117d5dc376363b03ffe3b06d4430a00a99ee922e6055",
    "b652278d24f9fca0754bfe08cbcf64da8e8b472e301df52c0273bef31d820c78",
    "b654444f839c6b4770a74f7ddfba494ece8fb4a603e24b89dcc6117cf44be03b",
    "b769d204d91d8c1d1d89f469597beeabeab12b010f8e96c4bb0d95a36efc7ea6",
    "b7a7dfbf3d0033db9b0783b254dfca567f438e85a36907347395baeceae45baf",
    "b7dd2be9dacf91ac95d23a67144094361a8d3c6c69c676a139dcb87379f7fc08",
    "ba5736651738f90c56b5da351baad9189a20571c3b42d8d827fb05f433c9e39d",
    "ba9b34a820494668042d75244b1f6aa8b33f8324b478151f479eec92eca6908c",
    "baf052e266954c1c7d8e414a5de8981dda046db548de2a420b19a1a799e45b9d",
    "bb08966f1dc5c235119a8326cfd8cc0ae5343c835d91d28f5d14fedddfd514c4",
    "bc8b24d70b6930ca2c3301f1b8db94c821063848fd576ee881c8d8a4f9983145",
    "bcf698dfcfaaa3c243b12572a8025436531eb48e7947d54b523e9a60df011ffb",
    "bda3dbc8b281f8f9d7720ff713993a11564ad604d25539659c85564a0b392225",
    "c248d37f35e7ae4c30bcb826e3608bafa25bedb88065bccef666f2123901d27f",
    "c781084cc61bed0b7f88c084d52d3eee439862195dc2456177dbeb3640849472",
    "c86ac71fecc4abe97cadd45fc5eb02703fc32b86186758645eddc9bb8232a4a5",
    "c8e305944b7450ca315f3b953fcf91fb15c28474dbbdf6e2a4c589b35b72a03a",
    "cb535d5fe58e4aa8131bbe728a71bbf47ed8190896be308eaffcca7a6924dbd5",
    "cbade5ea5e60a17ad034c3027bc0950894c817c8beb1b5a638c4b694ba15ee84",
    "cbb69ec9c153149033e4ed35b842c3c650455686bb1f55e0020ea2a4e11ba150",
    "ceffc7b749c167f1ef43b5ea2d14ddf68b4e6d322d63f9e7ebd44ee488a70a1a",
    "d0363f9df9a0e3253c3ca8a8c1129a7677f57ca8504f2b8c76d5d721b45b6aa1",
    "d04b9509187ced62f2b25bb43653432104d6ba20d347122b47c7ffeed92c676b",
    "d07e91d785643eff00fc8ea552a6cc53fa940527ea09186220e0e31ba386f505",
    "d0acee62826508ccfa5067f0c705e6ac79c92577a234e6f12e471e222fcb51ed",
    "d0bd7f013d810b9e3adf43e262f9a14212a082aecbcff745d38457725124bb25",
    "d4fea2bc2bf327c6fbf08fade6bd358d2278ffcca0f8d2f5f2401d1bf273cebf",
    "d8dd4e020ce2d871322aac919825451a4896837c26726fa97492f149c7ea160b",
    "d96446a38e196da024e66744647512866b9d41567a07b6f956b196cca5c45c78",
    "dd04dcccd187a9fa71155d43de189ef3fc529a674a8e91d8f1a13b253c36dd3d",
    "dd5ee9dc603c2001887533bf79ad718bc6bb422b8105abe63f37bc38ed8907d8",
    "de7ff587535fdec5a886ef5f70a697f8852010c63c6e11fe90a5f02450138444",
    "df7b89eadd7c0de9d8a5c2d3925c1b9b1d56a6394c786566bb710089ad86f3c5",
    "dfe53e1250d3e64040eb04763543312a93c3ef168b76179835b8fadf485fe44e",
    "e0dac1fba06bac9201d34757175b77ebf7995f65358ee6d0c691eaf64dc1d127",
    "e10cdbb1385f7c36f5ded37216480c428b90814a4a1dc0608bf7d1c70b59da5d",
    "e2b70526792c6027c6cdea07df23d2f231b2fd7c6b448525befb5cb19a9e7cc5",
    "e30e4707a712bbdeea64f522e5572e08baa47e23a9f2e9fceab08f5e1e59c499",
    "e3a88e5e45d359915242ed65625ff1239157264670571057b9d4d57411d280c2",
    "e4f3184e4bc96cd6cc91b7b98d0f6de25693bd01f1451b433f2544d6978ec52a",
    "e54ef4f5a6bc0ba4bd425236843943770543f539a3957015f9db4d9d93600d3d",
    "e5eeca6936df4f888c9edf7b86b47c8b5bd73fa7e9b10067ce41108a2758786e",
    "e7066edcf225a343715b11792d7e07fae98c6e444c16f4b5bb402be6f02e5062",
    "e710ff3f6e842f22ce0abb513f80d7f8aa21d9250eb982ad61d5cbe4692ec592",
    "e910d95453664456da36f018d9d2a792ee8f140fa231525c98ed6dff5f9034e7",
    "e9b92c131501a663400874b913d659906dfbfeaf42bc98674cb8029d438ec1de",
    "e9f16dcdb32d20c95e6ba8d964c1d06bfe8c3f937520a982c427d80563344e1d",
    "ebbb070d73a8c393db08a8fd898ea3256e154b486b71e8da3c263a09f70f7311",
    "ebee32c9a81589eb6573ae7e234d80a6e9232e616dab9e2d32ed4877000bd7ad",
    "ec231412e14cc6fe5a3f05a1197f3270a1bd1cdd48e8a6967e7262be54ac7bfd",
    "ed0964e233e772956827b3d30279e5136fc5dd441d1ad1935e53de99b704301d",
    "f11ba4f6997ae862a3cdf0eb3ec92c84186bac7f902021ed0a3f1f4fd74df342",
    "f2145211296ac056cc8ef449a890dbe353375bee997aad5c7f89233dfff140ce",
    "f28493d50689c0fdc2a6837094d9f1ed4e0a4916e5495ad310a2c9987d4715f3",
    "f7c30124f3067f6e539bf8a96ee2393ebee8c843672dd2c20b6d0e1ab77d22fe",
    "f8190af86696d4e067daa26a663e647e668683774d496b6598f7cc392466af5f",
    "fa8184fe66ba27f52dd36b365b53029cf3911720431d823f60b38ddd161833d2",
    "fc036b8d06b0e8272b97db4d3135a6c8dbb80e2d7de89cb07088416b61540e07",
    "fe2a8a0c1ce20d5ffcbef209a44dc4f3acf3ea5ed5b5773b52d667729e6691d9",
}
KINDS = ("max_lines|mentions_all|known_ids_only|clause_forbid|clause_require|clause_each_require|pace_near|"
         "time_near|require_any|forbid_any|protocol_lines|plan_parses|section_order|cjk_ratio")
KIND_OF = r"[\"']?kind[\"']?\s*[:=]\s*[\"']?"
# alert and card are ordinary words: a rule object of theirs is told by a key only their rules have.
OWN_KEYS = {"alert": r"must_reference_any|expect", "card": r"owner_duty|option_parse|meanwhile_forbid|options_min|options_max|no_score_executors"}
SHAPES = {
    "a rule object of the grader": re.compile(KIND_OF + r"(?:" + KINDS + r")\b"),
    "a question of the chief's exam": re.compile(r"[\"']?exam[\"']?\s*[:=]\s*[\"']?chief_of_staff\b"),
    "an answer kept as a control": re.compile(r"[\"']?item[\"']?\s*[:=]\s*[\"']Q[1-5][a-e][\"']"),
}
# What two files may hold of these shapes, and nothing more: this check's own made-up samples,
# and the made-up set that tests the Owner's put script. Each is a whole line as it stands today,
# kept as the sha256 of the stripped line with the times it may occur; those lines are taken out
# before the shapes are looked for, and the rest of the file is read like any other. A line that
# changes, or one more like it, is refused until it is listed here again (by hand, after reading).
SHAPE_ALLOWED: dict[str, dict[str, int]] = {
    "scripts/agentrt/test_no_exam_keys.py": {
        "0b5fae332f59a428837fcb438427724d394f58aea39722fef901dba21acdd591": 1,
        "0c043728ee673412b8bb329bb9f0f4b734edd1ab305e9b067828398cc873c1c7": 1,
        "6ae23e07db1114760fdcba4e1add46fb1e4dd3330cdde744ae6d164dac968762": 1,
        "806a7ee71d71c5df49f7d343ea16f0e41305f9bae0f634c511777f657aade401": 1,
        "87e3bff061bd7b985f56560279f45cd299ff379f9231fa2c0bb2bf212154c6a1": 1,
        "8b14db51415d57b2bfcd021da913a5052e293a76498b21d3e96cc694d427434a": 1,
        "98318ee60301122e31dd809c52ab8a7536e367a0fafae47a0baeb9b4703e02ad": 1,
        "9c1643b0c37c2a5a98e9e5dee4bbc8eb14b8c239c2f9bc239c5537a89ba7dafd": 1,
        "b4322958b85d5aebe1b1abeb29e33ab00e835ac25090c3ff88ebbd1225a1b67e": 1,
        "c946c2600fa0656619770ce6df99286b5af559a7e53d99e5dd83f029d41ac538": 1,
    },
    "scripts/agentrt/test_chief_exam_set.py": {
        "161577e3082d9eb13e6efd128fd352d8ac148b04c17ed299a020137f4546dbf4": 1,
        "5a45c0c1c5c25314ffe9267a13aa0b3614e5144db26a46691499451b2df46982": 1,
        "70ca64ff8096564510b20c2596cfb9a559a5186e2040bf0a45dcaf7a44a60454": 1,
        "f878d74d72976b8de3280c2204a3c42dcb0ee2dec476380964a41742b5632fb8": 1,
    },
}
TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){2,}")
ITEM_LINE = re.compile(r"^\s*(?:\|\s*|[-*•·]\s+|\d+[.)]\s+)?\**Q[1-5][a-e]\b", re.MULTILINE)
STRINGS = re.compile(r'"((?:[^"\\\n]|\\.){10,})"|\'((?:[^\'\\\n]|\\.){10,})\'|`([^`\n]{10,})`')
SET_FILE = re.compile(r"(^|/)(q[1-5]-[a-z0-9-]+\.json|controls\.json|grade_reference\.py)$")
MAX_BYTES = 8 << 20


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def tracked() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout
    return [p for p in out.decode().split("\0") if p]


def findings(path: str, body: str) -> list[str]:
    """What kinds of key a file holds: its path and the kind, never the key."""
    out = []
    if SET_FILE.search(path):
        out.append("a file of the set")
    for t in TOKEN.findall(body):
        parts = t.split("-")
        if any(sha("-".join(parts[i:j])) in RULE_ID_SHA256 for i in range(len(parts)) for j in range(i + 3, len(parts) + 1)):
            out.append("a rule id of the set")
            break
    lines = (ln.strip() for ln in body.splitlines())
    if any(sha(c) in PATTERN_SHA256 for c in candidates(body)) or any(len(ln) >= 10 and sha(ln) in PATTERN_SHA256 for ln in lines):
        out.append("a pattern of a rule")
    rest = shape_text(path, body)
    out += [name for name, rx in SHAPES.items() if rx.search(rest)]
    for kind, keys in OWN_KEYS.items():
        if re.search(KIND_OF + kind + r"\b", rest) and re.search(r"[\"']?(?:" + keys + r")[\"']?\s*[:=]", rest):
            out.append("a rule object of the grader")
    if len(ITEM_LINE.findall(body)) >= 3:
        out.append("rows or items of the sub-questions")
    return out


def shape_text(path: str, body: str) -> str:
    """body without the lines SHAPE_ALLOWED lists for path, each as many times as it may occur."""
    allowed = collections.Counter(SHAPE_ALLOWED.get(path, {}))
    if not allowed:
        return body
    keep = []
    for ln in body.splitlines():
        h = sha(ln.strip())
        if allowed[h] > 0:
            allowed[h] -= 1
        else:
            keep.append(ln)
    return "\n".join(keep)


def candidates(body: str) -> list[str]:
    """The quoted (double or single) and backticked strings of 10 characters or more."""
    return [a or b or c for a, b, c in STRINGS.findall(body)]


def read(path: str, root: Path = ROOT) -> tuple[str | None, str]:
    """A tracked file's text (bytes it cannot decode are replaced, so a binary is scanned too; a
    symbolic link is its target's text, as git keeps it, never followed), or why it was not read."""
    p = root / path
    if p.is_symlink():
        return os.readlink(p), ""
    if not p.is_file():
        return None, "tracked but not a file here, not scanned"
    if p.stat().st_size > MAX_BYTES:
        return None, f"over {MAX_BYTES >> 20} MiB, not scanned"
    return p.read_bytes().decode("utf-8", errors="replace"), ""


def test_the_fingerprints_are_there() -> None:
    assert len(RULE_ID_SHA256) >= 20 and len(PATTERN_SHA256) >= 100
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in RULE_ID_SHA256 | PATTERN_SHA256)


def test_no_tracked_file_holds_a_key() -> None:
    bad = []
    for path in tracked():
        body, why = read(path)
        if why:
            bad.append(f"{path}: {why}")
        elif body is not None:
            bad += [f"{path}: {what}" for what in findings(path, body)]
    assert bad == [], "the chief exam's grading keys in the repository (TD-396): " + "; ".join(bad)


def test_the_shapes_it_refuses() -> None:
    # Made-up stand-ins of each shape: none of them is a key of the set.
    for path, body, kind in [
        ("notes/a.md", 'see `{"id": "x", "kind": "clause_forbid", "aliases": ["a"]}`', "a rule object of the grader"),
        ("notes/b.yaml", "kind: protocol_lines\nprefix: X", "a rule object of the grader"),
        ("notes/c.json", '{"exam": "chief_of_staff", "items": []}', "a question of the chief's exam"),
        ("notes/d.json", '[{"item": "Q3a", "expect": "pass", "answer": "..."}]', "an answer kept as a control"),
        ("notes/e.md", "- Q1a: x\n- Q2a: y\n* **Q3b** z\n", "rows or items of the sub-questions"),
        ("notes/f.md", "| Q1a | x |\n| Q1b | y |\n| Q2a | z |\n", "rows or items of the sub-questions"),
        ("notes/h.json", '{"id": "r", "kind": "alert", "expect": true, "must_reference_any": ["x"]}', "a rule object of the grader"),
        ("notes/k.json", '{"kind": "alert", "expect": false, "hard": true}', "a rule object of the grader"),
        ("notes/i.json", '{"kind": "card", "owner_duty": "rule", "options_min": 2}', "a rule object of the grader"),
        # an exempt file passes only its listed lines: another rule object there is refused
        ("scripts/agentrt/test_chief_exam_set.py", '{"kind": "clause_forbid", "forbid": ["x"]}', "a rule object of the grader"),
        ("other/q2-anything.json", "{}", "a file of the set"),
        ("other/controls.json", "[]", "a file of the set"),
    ]:
        assert kind in findings(path, body), (path, findings(path, body))
    # A rule id inside a longer word, and a pattern as JSON or code, are found by fingerprint:
    # take any fingerprinted id or pattern, which this test cannot name, so check the mechanism.
    assert findings("notes/g.md", "ordinary-words-only and `a long ordinary phrase`") == []
    # alert and card alone are words, not rule objects
    assert findings("notes/j.yaml", "kind: alert\nseverity: page\n") == []
    # single-quoted strings are read too, escapes kept as written
    assert candidates("x = 'a pattern of [ten]+' and \"another one here\" and `a third in ticks`") == [
        "a pattern of [ten]+", "another one here", "a third in ticks"]


def test_an_exempt_file_passes_only_its_listed_lines() -> None:
    # Review 470 B2: a rule object of a kind the file already holds, appended, is still refused.
    for path in SHAPE_ALLOWED:
        body, why = read(path)
        assert body is not None and not why, path
        assert findings(path, body) == [], path
        more = body + "\n" + '{"kind": "require_any", "any_of": ["ordinary synthetic text"]}' + "\n"
        assert "a rule object of the grader" in findings(path, more), path
        twice = body + "\n" + body.splitlines()[-1]
        assert findings(path, twice) == findings(path, body + "\n"), path


def test_a_link_or_a_missing_file_is_not_skipped() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "real.md").write_text("plain")
        os.symlink("a target that names something", root / "link.md")
        assert read("link.md", root) == ("a target that names something", "")
        assert read("gone.md", root) == (None, "tracked but not a file here, not scanned")
        (root / "big.bin").write_bytes(b"x" * (MAX_BYTES + 1))
        assert read("big.bin", root)[1].startswith("over ")
        assert read("real.md", root) == ("plain", "")


def staged() -> int:
    """The pre-commit check: the staged copy of every file the commit adds or changes."""
    names = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                           check=True, capture_output=True).stdout.decode().split("\0")
    bad = []
    for path in filter(None, names):
        size = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-s", ":" + path], capture_output=True, text=True)
        if size.returncode != 0:
            bad.append(f"{path}: its staged copy cannot be read")
            continue
        if int(size.stdout.strip() or 0) > MAX_BYTES:
            bad.append(f"{path}: over {MAX_BYTES >> 20} MiB, not scanned")
            continue
        blob = subprocess.run(["git", "-C", str(ROOT), "show", ":" + path], capture_output=True)
        if blob.returncode != 0:
            bad.append(f"{path}: its staged copy cannot be read")
            continue
        bad += [f"{path}: {what}" for what in findings(path, blob.stdout.decode("utf-8", errors="replace"))]
    for line in bad:
        print(f"pre-commit: the chief exam's grading keys stay out of the repository (TD-396): {line}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--staged"]:
        sys.exit("usage: test_no_exam_keys.py --staged")
    sys.exit(staged())
