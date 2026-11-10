// 虎扑 goblin.hupu.com 广告接口清理。
// 派生自 https://github.com/akaagiao1/quantumult-x-scripts 的 hupu-ad-test.js
// （8.2.67 抓包）。与原脚本的差别只有两处：
//   1. 版本号不再写死，按 3/<任意版本>/ 匹配，App 升级后不会静默失效；
//   2. 不再要求 ad_code === 1，只要 ads 是非空数组就清空，其他字段原样保留。
(function () {
  try {
    var url = $request.url || "";
    var pattern = /^https:\/\/goblin\.hupu\.com\/3\/[0-9]+\.[0-9]+\.[0-9]+\/interfaceAd\/getOther\/(v3|batch)(\?|$)/;
    if (!pattern.test(url) || typeof $response.body !== "string") return $done({});
    var data = JSON.parse($response.body);
    if (!data || typeof data !== "object" || Array.isArray(data)) return $done({});
    if (!Array.isArray(data.ads) || data.ads.length === 0) return $done({});
    data.ads = [];
    return $done({ body: JSON.stringify(data) });
  } catch (e) { return $done({}); }
})();