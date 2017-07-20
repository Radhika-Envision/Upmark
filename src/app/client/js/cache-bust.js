'use strict';

angular.module('upmark.cache_bust', ['upmark.settings'])


/*
 * Install an HTTP interceptor to add version numbers to the URLs of certain
 * resources. This is to improve the effectiveness of the browser cache, and to
 * give control over when the cache should be invalidated.
 */
 .config(['$httpProvider', 'versionedResources', 'version',
     function($httpProvider, versionedResources, version) {
         var rs = versionedResources.map(function(r) {
             r._patterns = r.patterns.map(function(p) {
                 return new RegExp(p);
             });
             r.matches = function(path) {
                 var test = function(pattern) {
                     return pattern.test(path);
                 };
                 return r._patterns.some(test);
             };
             return r;
         });
         var getVersionRule = function(path) {
             for (var i = 0; i < rs.length; i++) {
                 var r = rs[i];
                 if (r.matches(path))
                     return r.when;
             }
             return 'never';
         };
         var seq = 0;
         var lastTimestamp = null;
         var getTimestamp = function() {
             var ts = Date.now() / 1000;
             if (ts == lastTimestamp)
                 seq += 1;
             else
                 seq = 0;
             lastTimestamp = ts;
             return '' + ts + '-' + seq;
         };


         $httpProvider.interceptors.push([function() {
             return {
                 request: function(config) {
                     var vrule = getVersionRule(config.url);
                     if (vrule == 'never')
                         return config;

                     var versionString = version[vrule];
                     if (!versionString)
                         return config;
                     if (versionString == 'vv')
                         versionString = 'vv_' + getTimestamp();

                     if (config.url.indexOf('?') == -1)
                         config.url += '?v=' + versionString;
                     else
                         config.url += '&v=' + versionString;
                     return config;
                 }
             }
         }]);
     }
 ])

;
