'use strict';

angular.module('upmark.route_version', [])


.run(function($rootScope, $window, $location, Notifications, log,
        $route, checkLogin, $q, QuestionNode) {

    // Upgrade route version
    // The route version should be a number in the range 0-z
    $rootScope.$on('$routeChangeStart', function(event, next, current) {
        var CURRENT_VERSION = 2;
        // Initialise from $location because it is aware of the hash. This
        // should probably work with HTML5 mode URLs too.
        var createUrl = function(urlOrStr) {
            var url = new Url(urlOrStr.toString());
            // Hacks for IE 11 because realitve URL construction doesn't work
            // https://github.com/Mikhus/domurl/issues/6
            url.host = url.port = url.protocol = '';
            if (!url.path) {
                url.path = '/';
            }
            return url;
        };
        var originalUrl = createUrl($location.url() || '/');

        var vmatch = /^\/([0-9a-z])\//.exec(originalUrl.path);
        var version = Number(vmatch && vmatch[1] || '0');

        if (version >= CURRENT_VERSION)
            return;
        event.preventDefault();

        // Special case for root location, since it gets used a lot (landing
        // page).
        if (originalUrl.toString() == '/') {
            $location.url('/' + CURRENT_VERSION + '/');
            return;
        }

        var deferred = $q.defer();
        deferred.resolve(originalUrl);
        var promise = deferred.promise;

        if (version < 1) {
            promise = promise.then(function(oldUrl) {
                // Version 1: Rename:
                //  - survey -> program
                //  - hierarchy -> survey
                //  - assessment -> submission
                var url = createUrl(oldUrl);
                var pElems = url.path.split('/').map(function(elem) {
                    if (elem == 'survey')
                        return 'program';
                    else if (elem == 'surveys')
                        return 'programs';
                    else if (elem == 'hierarchy')
                        return 'survey';
                    else if (elem == 'assessment')
                        return 'submission';
                    else
                        return elem;
                });
                pElems.splice(1, 0, '1');
                url.path = pElems.join('/');

                if (url.query.survey) {
                    url.query.program = url.query.survey;
                    delete url.query.survey;
                }
                if (url.query.hierarchy) {
                    url.query.survey = url.query.hierarchy;
                    delete url.query.hierarchy;
                }
                if (url.query.assessment) {
                    url.query.submission = url.query.assessment;
                    delete url.query.assessment;
                }
                if (url.query.assessment1) {
                    url.query.submission1 = url.query.assessment1;
                    delete url.query.assessment1;
                }
                if (url.query.assessment2) {
                    url.query.submission2 = url.query.assessment2;
                    delete url.query.assessment2;
                }
                return url;
            });
        }

        if (version < 2) {
            promise = promise.then(function(oldUrl) {
                // Version 2: When accessing a measure, replace parent ID with
                // survey ID - except for new measures.
                var url = createUrl(oldUrl);
                var measureMatch = /^\/1\/measure\/([\w-]+)/.exec(oldUrl);
                var subPromise = null;
                if (measureMatch && measureMatch[1] != 'new') {
                    subPromise = QuestionNode.get({
                        id: url.query.parent,
                        programId: url.query.program,
                    }).$promise.then(function(qnode) {
                        url.query.survey = qnode.survey.id;
                        delete url.query.parent;
                    });
                }
                return $q.when(subPromise).then(function() {
                    url.path = url.path.replace(/^\/\d+\//, '/2/');
                    return url;
                });
            });
        }

        promise.then(function(newUrl) {
            console.log('Upgraded route to v' + CURRENT_VERSION +
                ':\n' + originalUrl + '\n' + newUrl);
            $location.url(newUrl);
        });
    });

    $rootScope.$on('$routeChangeError',
            function(event, current, previous, rejection) {
        var error;
        if (rejection && rejection.statusText)
            error = rejection.statusText;
        else if (rejection && rejection.message)
            error = rejection.message;
        else if (angular.isString(rejection))
            error = rejection;
        else
            error = "Object not found";
        log.error("Failed to navigate to {}", $location.url());
        Notifications.set('route', 'error', error, 10000);

        checkLogin().then(
            function sessionStillValid() {
                if (previous)
                    $window.history.back();
            },
            function sessionInvalid() {
                Notifications.set('route', 'error',
                    "Your session has expired. Please log in again.");
            }
        );
    });

    $rootScope.$on('$routeChangeSuccess', function(event) {
        $window.ga('send', 'pageview', '/' + $route.current.loadedTemplateUrl);
    });
})

;
