# advert.x —— 手工补充层（对上游组打底的补充；上游生成物在 data/upstream/，会被构建覆盖）
# 语法同 dlc domain-list：domain:x = x 及其子域；full:x = 仅精确匹配
#
# 推特（X）广告与分析端点。**刻意不含 twitter.com / x.com / t.co 本体** ——
# 那是推特服务与短链本体，拦掉会直接断掉推特与站外推文链接。
# （实探：ads-twitter.com 父域无 A 记录，但 static.ads-twitter.com 可解析，后缀仍覆盖它）
#
domain:ads-twitter.com
domain:ads.twitter.com
domain:ads.x.com
domain:analytics.twitter.com
