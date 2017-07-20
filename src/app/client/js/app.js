'use strict';

angular.module('upmark', [
    'angular-input-stars',
    'angular-medium-editor',
    'angular-select-text',
    'cfp.hotkeys',
    'diff-match-patch',
    'msieurtoph.ngCheckboxes',
    'ngAnimate',
    'ngRoute',
    'ui.bootstrap',
    'ui.bootstrap.showErrors',
    'upmark.admin.settings',
    'upmark.authz',
    'upmark.cache_bust',
    'upmark.chain',
    'upmark.current_user',
    'upmark.custom',
    'upmark.diff',
    'upmark.group',
    'upmark.home',
    'upmark.location',
    'upmark.notifications',
    'upmark.organisation',
    'upmark.response.type',
    'upmark.root',
    'upmark.route_version',
    'upmark.settings',
    'upmark.statistics',
    'upmark.subscription',
    'upmark.submission.approval',
    'upmark.submission.export',
    'upmark.submission.header',
    'upmark.submission.response',
    'upmark.submission.rnode',
    'upmark.submission.select',
    'upmark.submission.submission',
    'upmark.survey',
    'upmark.survey.history',
    'upmark.survey.layout',
    'upmark.survey.measure',
    'upmark.survey.program',
    'upmark.survey.qnode',
    'upmark.structure',
    'upmark.survey.survey',
    'upmark.system',
    'upmark.user',
    'validation.match',
    'vpac.utils.arrays',
    'vpac.utils.events',
    'vpac.utils.logging',
    'vpac.utils.math',
    'vpac.utils.observer',
    'vpac.utils.queue',
    'vpac.utils.requests',
    'vpac.utils.session',
    'vpac.utils.string',
    'vpac.utils.cycle',
    'vpac.utils.watch',
    'vpac.widgets.any-href',
    'vpac.widgets.dimmer',
    'vpac.widgets.docs',
    'vpac.widgets.editor',
    'vpac.widgets.form-controls',
    'vpac.widgets.markdown',
    'vpac.widgets.page-title',
    'vpac.widgets.progress',
    'vpac.widgets.size',
    'vpac.widgets.spinner',
    'vpac.widgets.text',
    'vpac.widgets.time',
    'vpac.widgets.visibility',
    'yaru22.angular-timeago',
])


.config(function($locationProvider) {
    // Revert behaviour: URLs do not need to have a `!` prefix.
    // https://github.com/angular/angular.js/commit/aa077e81129c740041438688dff2e8d20c3d7b52
    // https://webmasters.googleblog.com/2015/10/deprecating-our-ajax-crawling-scheme.html
    $locationProvider.hashPrefix('');
})


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .otherwise({
            resolve: {error: ['$q', function($q) {
                return $q.reject({statusText: "That page does not exist"});
            }]}
        });
})


.config(function(logProvider) {
    logProvider.setLevel('info');
})


.config(function($animateProvider) {
    $animateProvider.classNameFilter(/animate/);
})


.config(function($httpProvider) {
    // Set up XSRF protection for Tornado.
    // http://tornado.readthedocs.org/en/branch4.0/web.html#tornado.web.RequestHandler.check_xsrf_cookie
    $httpProvider.defaults.xsrfCookieName = '_xsrf';
    $httpProvider.defaults.xsrfHeaderName = 'X-Xsrftoken';
})


/*
 * Install an HTTP interceptor to make error reasons easier to use. All HTTP
 * responses will have the "reason" in the statusText field.
 */
.config(function($httpProvider) {
    $httpProvider.interceptors.push(['$q', function($q) {
        return {
            response: function(response) {
                var reason = response.headers('Operation-Details');
                if (reason)
                    response.statusText = reason;
                return response;
            },
            responseError: function(rejection) {
                if (!rejection.headers)
                    return $q.reject(rejection);
                var reason = rejection.headers('Operation-Details');
                if (reason)
                    rejection.statusText = reason;
                return $q.reject(rejection);
            }
        };
    }]);
})


/*
 * Global config for some 3rd party libraries.
 */
.config(function() {
    Dropzone.autoDiscover = false;
})


.run(['$cacheFactory', '$http', function($cacheFactory, $http) {
    $http.defaults.cache = $cacheFactory('lruCache', {capacity: 100});
}])


.factory('Authz', function(AuthzPolicy, currentUser, $cookies) {
    var policyFactory = function(context) {
        var localPolicy = policyFactory.rootPolicy.derive(context);
        return function(ruleName) {
            return localPolicy.check(ruleName);
        };
    };
    policyFactory.rootPolicy = new AuthzPolicy(null, null, null, 'client');

    policyFactory.rootPolicy.context.s = {
        user: currentUser,
        org: currentUser.organisation,
        superuser: !!$cookies.get('superuser'),
    };

    return policyFactory;
})


.config(function(timeAgoSettings) {
    var oneDay = 60 * 60 * 24;
    timeAgoSettings.allowFuture = true;
    timeAgoSettings.fullDateAfterSeconds = oneDay * 3;
})

;
