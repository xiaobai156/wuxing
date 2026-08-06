from __future__ import annotations

import re


BROWSER_TAB_CLICK_PATTERNS: dict[str, re.Pattern[str]] = {
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/": re.compile(r"^杀一行$"),
}


BROWSER_FIRST_URLS = {
    "https://jjlachsn.4fk3e-i2rpf-vgknlh.work:16677/topic/660782.html",
    "https://gboqrz.1grys-bnkqq-evlqkb.work/topic/507999.html",
    "https://jnf52f.mjhbr-zqt9a-ofmjce.work/topic/488506.html",
    "https://ezovboxw.uomne-2a0nc-yjyzjh.xyz:16677/topic/320728.html",
    "https://v0uer.e2xs0-3tuvc-rsgtzx.xyz/topic/255638.html",
    "https://nxtoep.9at21-abkka-svfjrm.xyz:16677/topic/547559.html",
    "https://xjohxjqz.s5luy-wevrh-gnxone.xyz:16677/topic/247280.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626030.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/625515.html",
    "https://sgxozo.4b5jw-x2zou-ukbybu.xyz:16677/topic/267706.html",
    "https://jogavu.6bl6s-ilo1w-yfnvvl.work:16677/topic/678127.html",
    "https://6f4poq.7uyqo-2dy2h-jiepqa.work/topic/485549.html",
    "https://sqddimfu.evs71-kia2b-gshsdc.xyz:16677/topic/226258.html",
    "https://qzpwvvvb.a3qgk-l2h5k-opahdg.xyz:16677/topic/254842.html",
    "https://gboqrz.sm0a0-x9x2c-xyvjdr.work/topic/205464.html",
    "https://rh2fgz.a96ub-s6g0d-mfbdwp.work/topic/206556.html",
    "https://pwqviw.1tcpi-45qgo-qddfnk.work:16677/topic/272922.html",
    "https://vmfvzmh.7jh1y-qgjk8-lavfxb.work:16677/topic/782038.html",
    "https://odyaxne.1k8bk-9hlzy-spgmbw.xyz:16677/topic/446757.html",
    "https://yqjfwqsc.1dayz-aetgp-kbjidr.xyz:16677/topic/637955.html",
    "https://tjetrfr.jocy8-cy4wk-fmpeer.xyz:16677/",
    "https://wxaxdfc.523mo-z7mla-owjdon.xyz:16677/",
    "https://uinpwmgx.5jl59-ok78a-ctvois.xyz:16677/topic/448284.html",
    "https://hl.www25195a.com/read.php?tid=607",
    "https://kxglojup.fao5v-9u0oz-okhubb.work:16677/topic/782072.html",
    "https://bbuueerm.pxcma-jyfok-mvduyw.xyz:16633/topic/455269.html",
    "https://hhsmgw.rcl5b-akta2-ylzzwv.xyz:16677/topic/282006.html",
    "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/727455.html",
    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626097.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/625994.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626101.html",
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/",
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am",
    "https://2.www39169b.com:888/#62111",
    "https://dzuojaf.rua12-mwvo8-oriqfc.xyz:16677/topic/461725.html",
    "https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/",
    "https://yqjfwqsc.1dayz-aetgp-kbjidr.xyz:16677/topic/682017.html",
    "https://mfhfepu.ow55j-i5hbb-icetss.xyz/topic/768602.html",
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/677751.html",
    "https://nyekjhvz.kr4ar-cgeaj-aekfox.xyz:16677/",
    "https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/453352.html",
    "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/",
    "https://cxmdjok.8wtwc-boven-glylvt.xyz:16677/topic/437741.html",
    "https://fszatrw.xhwqs-gffny-zzdfsq.work:16677/topic/678240.html",
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/455533.html",
    "https://g63.52619c.com:8443/tie1/1614.html",
    "https://3.www112291a.com:2053/gengxin/16.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/467884.html",
    "https://uqhuqalo.vbcyr-idr4l-jouqgu.xyz:16633/topic/417591.html",
    "https://gboqrz.d2cda-p5u2y-gwxmnf.work/topic/465446.html",
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280932.html",
    "https://cwaskgxv.hzpd5-2r09a-wieopn.xyz:16677/topic/282016.html",
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/461374.html",
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html",
    "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html",
    "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626065.html",
    "https://pwqviw.1tcpi-45qgo-qddfnk.work:16677/topic/291140.html",
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/469841.html",
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/227015.html",
    "https://msbqxti.zhx2n-7v5x3-ivdpud.xyz:16677/topic/677880.html",
    "https://qnbezan.l1qb0-icltl-eyddev.xyz:16677/topic/504956.html",
    "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/454773.html",
    "https://jdjzpkce.osyaf-gxlte-otlblr.xyz:16677/",
    "https://myvvqq.30dok-2s9fd-bibfmg.work/",
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/682107.html",
}


BROWSER_VISIBLE_TEXT_ONLY_URLS = {
    "https://hl.www25195a.com/read.php?tid=607",
    "https://kxglojup.fao5v-9u0oz-okhubb.work:16677/topic/782072.html",
    "https://bbuueerm.pxcma-jyfok-mvduyw.xyz:16633/topic/455269.html",
    "https://hhsmgw.rcl5b-akta2-ylzzwv.xyz:16677/topic/282006.html",
    "https://wmdhoki.6su07-7lpw6-gudkzl.xyz:16677/topic/727455.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626097.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/625994.html",
    "https://eebysckd.2go6k-y0pfv-fqbdsm.xyz:16677/topic/626101.html",
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/682107.html",
    "https://dzuojaf.rua12-mwvo8-oriqfc.xyz:16677/topic/461725.html",
    "https://yqjfwqsc.1dayz-aetgp-kbjidr.xyz:16677/topic/682017.html",
    "https://mfhfepu.ow55j-i5hbb-icetss.xyz/topic/768602.html",
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/677751.html",
    "https://nyekjhvz.kr4ar-cgeaj-aekfox.xyz:16677/",
    "https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/453352.html",
    "https://cxmdjok.8wtwc-boven-glylvt.xyz:16677/topic/437741.html",
    "https://fszatrw.xhwqs-gffny-zzdfsq.work:16677/topic/678240.html",
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/455533.html",
    "https://g63.52619c.com:8443/tie1/1614.html",
    "https://3.www112291a.com:2053/gengxin/16.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/467884.html",
    "https://uqhuqalo.vbcyr-idr4l-jouqgu.xyz:16633/topic/417591.html",
    "https://gboqrz.d2cda-p5u2y-gwxmnf.work/topic/465446.html",
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html",
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280932.html",
    "https://cwaskgxv.hzpd5-2r09a-wieopn.xyz:16677/topic/282016.html",
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/461374.html",
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html",
    "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/",
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/677608.html",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://fhktrabu.zbfrm-uzct1-pmycbu.xyz:16677/topic/469065.html",
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/",
    "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/",
    "https://993345.com/gsb1.aspx?id=1482",
    "https://zxliojf.83gjk-dnne7-kuyach.xyz:16677/",
    "https://2.www39169b.com:888/#62111",
    "https://myvvqq.30dok-2s9fd-bibfmg.work/",
    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
    # The source contains unrelated hidden article rows; the visible target
    # block is the authoritative boundary for this long page.
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am",
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/469841.html",
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/227015.html",
    "https://msbqxti.zhx2n-7v5x3-ivdpud.xyz:16677/topic/677880.html",
    "https://qnbezan.l1qb0-icltl-eyddev.xyz:16677/topic/504956.html",
    "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/454773.html",
}


BROWSER_SKIP_CLICK_URLS = {
    "https://2.www39169b.com:888/#62111",
    "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/464877.html",
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3475",
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/3031",
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/",
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/439186.html",
    "https://evvuoswc.2n3pw-mjk5d-wndmjh.xyz:16677/topic/287366.html",
    "https://zcphjs.ce83x-ms2rz-orwude.work:12277/#/users/116157",
    "https://skgdjjmz.l54vq-9httr-cmdnip.work:29477/article/admin/6a042f7e4ea5c20141013e17?url=xdr",
    "https://flrmed.u3l95-7ktwf-clwwtq.work:29455/article/admin/6a13fd7b741e3e91a04e59d1?url=sgnn",
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am",
}


BROWSER_NON_BLOCKING_LOAD_URLS = {
    "https://pxgaayml.2wyk5-dwn70-cljflt.xyz:16677/topic/458324.html",
    "https://2.www39169b.com:888/#62111",
    "https://dzuojaf.rua12-mwvo8-oriqfc.xyz:16677/topic/461725.html",
}


BROWSER_NO_SCROLL_URLS = {
    "https://myvvqq.30dok-2s9fd-bibfmg.work/",
}


ARTICLE_API_AUTHORITATIVE_ONLY_URLS = {
    "https://cahgjib.5blx9-z8506-ekiwxc.work:29488/article/admin/6a1449c2597e16d57eacb67a?url=lqz",
}


BROWSER_EXACT_CLICK_HREFS = {}


BROWSER_POPUP_CLOSE_SELECTORS = {
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/": "#pop-xyz .pop-xyz-close",
}


ARTICLE_API_CONFIGURED_REGION_FALLBACK_URLS = {
    "https://zlkcyl.e6mlx-wj46o-rzcukg.work:29499/article/admin/6a081678e0d076537e1df816?url=hyl",
}


BROWSER_REQUIRED_TEXT_PATTERNS: dict[str, re.Pattern[str]] = {
    "https://swnrapsd.74wyl-mm601-cbpzhn.xyz:16677/": re.compile(
        r"(?:^|[\r\n])[ \t]*杀一行[ \t]*(?:[\r\n])[\s\S]{0,120}?稳杀\s*[（(]?\s*1\s*[)）]?\s*行",
    ),
    "https://dzuojaf.rua12-mwvo8-oriqfc.xyz:16677/topic/461725.html": re.compile(
        r"必杀\s*一\s*行[\s\S]{0,120}?而立之年"
    ),
    "https://huqtzej.vvlq2-j4i8n-lisghq.xyz:16677/": re.compile(
        r"藏宝图[\s\S]{0,100}?稳杀\s*一\s*行"
    ),
    "https://yqjfwqsc.1dayz-aetgp-kbjidr.xyz:16677/topic/682017.html": re.compile(
        r"算法文心[\s\S]{0,200}?绝杀\s*[（(]?\s*1\s*[)）]?\s*行"
    ),
    "https://mfhfepu.ow55j-i5hbb-icetss.xyz/topic/768602.html": re.compile(
        r"四行中特[\s\S]{0,100}?北悸安涼"
    ),
    "https://ykeejph.z9koz-18xjn-pvglgy.xyz:16677/topic/677751.html": re.compile(
        r"歧路亡羊[\s\S]{0,120}?绝杀\s*一\s*行"
    ),
    "https://nyekjhvz.kr4ar-cgeaj-aekfox.xyz:16677/": re.compile(
        r"澳门创富[\s\S]{0,80}?绝杀\s*一\s*行"
    ),
    "https://tulprhfc.wghcb-bnmgm-hyymaz.work:16655/topic/453352.html": re.compile(
        r"平特网心水[\s\S]{0,60}?绝杀\s*一\s*行"
    ),
    "https://yylxuru.en4hs-c1zt6-qzcdin.xyz:16677/": re.compile(
        r"金吊桶[\s\S]{0,80}?绝杀\s*一\s*行"
    ),
    "https://cxmdjok.8wtwc-boven-glylvt.xyz:16677/topic/437741.html": re.compile(
        r"绝杀\s*一\s*行[\s\S]{0,120}?置身事外"
    ),
    "https://fszatrw.xhwqs-gffny-zzdfsq.work:16677/topic/678240.html": re.compile(
        r"精华资料\s*\d+期[\s\S]{0,100}?作者\s*[:：]\s*低眉折腰"
    ),
    "https://jldzuea.0xkqd-q7ng5-boerfb.xyz:16677/topic/455533.html": re.compile(
        r"零零散散[\s\S]{0,200}?绝杀\s*[（(]?\s*1\s*[)）]?\s*行"
    ),
    "https://g63.52619c.com:8443/tie1/1614.html": re.compile(
        r"产生共鸣[\s\S]{0,120}?稳杀\s*一\s*行"
    ),
    "https://3.www112291a.com:2053/gengxin/16.html": re.compile(
        r"狀元紅[\s\S]{0,100}?绝杀\s*[①1]\s*行"
    ),
    "https://fzzmqscl.bdppk-lyf4y-teyajr.xyz:16677/topic/467884.html": re.compile(
        r"豪放不羁[\s\S]{0,100}?绝杀\s*一\s*行"
    ),
    "https://uqhuqalo.vbcyr-idr4l-jouqgu.xyz:16633/topic/417591.html": re.compile(
        r"今非昔比[\s\S]{0,120}?绝杀\s*[①1一]\s*行"
    ),
    "https://gboqrz.d2cda-p5u2y-gwxmnf.work/topic/465446.html": re.compile(
        r"绝杀\s*一\s*行[\s\S]{0,120}?千言万语"
    ),
    "https://ekhivjcg.llnnt-l11x5-bywtoe.xyz:16677/topic/469882.html": re.compile(
        r"绝杀\s*一\s*行[\s\S]{0,120}?损人利己"
    ),
    "https://kfsujebc.djiz8-4tqt6-hubani.xyz:16677/topic/280932.html": re.compile(
        r"稳杀\s*一\s*行[\s\S]{0,140}?一呼百应"
    ),
    "https://cwaskgxv.hzpd5-2r09a-wieopn.xyz:16677/topic/282016.html": re.compile(
        r"绝杀\s*一\s*行[\s\S]{0,120}?猪狗不如"
    ),
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/461374.html": re.compile(
        r"绝杀\s*一\s*行[\s\S]{0,120}?降龙有悔"
    ),
    "https://useaul.z3rj5-9jlwg-dynocd.xyz:16677/topic/384879.html": re.compile(
        r"满汉全席[\s\S]{0,100}?绝杀\s*一\s*行"
    ),
    "https://zqliou.kify1-fbyi6-lmeykn.xyz:16677/": re.compile(
        r"澳门信封论坛[\s\S]{0,160}?绝杀\s*一\s*行"
    ),
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/469841.html": re.compile(
        r"特料帖\s*\d+期[\s\S]{0,80}?作者\s*[:：]\s*桃李不言"
    ),
    "https://e7rzi6.t5ti5-at6k5-fugxpa.work/topic/227015.html": re.compile(
        r"绝杀料\s*\d+期[\s\S]{0,80}?作者\s*[:：]\s*同心叶力"
    ),
    "https://cwdcaqzn.7mj0h-75k3q-cbuvqb.work:16677/#am": re.compile(
        r"八级心动.{0,40}?绝杀\s*一\s*行"
    ),
    "https://msbqxti.zhx2n-7v5x3-ivdpud.xyz:16677/topic/677880.html": re.compile(
        r"摇摇晃晃[\s\S]{0,100}?绝杀\s*一\s*行"
    ),
    "https://qnbezan.l1qb0-icltl-eyddev.xyz:16677/topic/504956.html": re.compile(
        r"夜泊秦淮[\s\S]{0,100}?绝杀\s*一\s*行"
    ),
    "https://buzfwpox.pwp8o-vfhi5-xmrytn.xyz:16677/topic/454773.html": re.compile(
        r"满面春风[\s\S]{0,100}?稳杀\s*一\s*行"
    ),
}


CLICK_THROUGH_DETAIL_URLS = {
    "https://mxiscni.nkh6s-vfni4-lwgfvw.xyz:16677/topic/257907.html",
}
