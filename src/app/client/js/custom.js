'use strict';

angular.module('upmark.custom', [
    'ui.select', 'ui.sortable', 'upmark.user', 'upmark.chain'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/custom', {
            templateUrl : 'custom_list.html',
            controller : 'CustomListCtrl',
        })
        .when('/:uv/custom/new', {
            templateUrl : 'custom.html',
            controller : 'CustomCtrl',
            resolve: {routeData: chainProvider({
                config: ['CustomQueryConfig', function(CustomQueryConfig) {
                    return CustomQueryConfig.get({}).$promise;
                }],
                duplicate: ['CustomQuery', '$route', function(CustomQuery, $route) {
                    var id = $route.current.params.duplicate;
                    if (!id)
                        return null;
                    return CustomQuery.get({id: id}).$promise;
                }],
            })}
        })
        .when('/:uv/custom/:id', {
            templateUrl : 'custom.html',
            controller : 'CustomCtrl',
            resolve: {routeData: chainProvider({
                config: ['CustomQueryConfig', function(CustomQueryConfig) {
                    return CustomQueryConfig.get({}).$promise;
                }],
                query: ['CustomQuery', '$route', function(CustomQuery, $route) {
                    var id = $route.current.params.id;
                    if (id == 'new')
                        return null;
                    return CustomQuery.get({id: id}).$promise;
                }],
            })}
        })
    ;
})


.factory('CustomQuery', ['$resource', function($resource) {
    return $resource('/custom_query/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET', url: '/custom_query/:id/history.json',
            isArray: true, cache: false },
        remove: { method: 'DELETE', cache: false },
    });
}])


.factory('CustomQueryConfig', ['$resource', function($resource) {
    return $resource('/report/custom_query/config.json', {}, {
        get: { method: 'GET', cache: false },
    });
}])


.factory('CustomQuerySettings', function() {
    return {
        autorun: true,
        limit: 20,
        wall_time: 0.5,
    };
})


.controller('CustomCtrl',
            function($scope, $http, Notifications, hotkeys, routeData,
                download, CustomQuery, $q, Editor, Authz,
                $location, CustomQuerySettings, Enqueue) {
    $scope.config = routeData.config;
    if (routeData.query) {
        $scope.query = routeData.query;
    } else if (routeData.duplicate) {
        $scope.query = new CustomQuery(routeData.duplicate);
        $scope.query.id = null;
    } else {
        $scope.query = new CustomQuery({
            description: null,
            text:   "-- This example query lists all users. " +
                        "Replace with your own code.\n" +
                    "-- Expand Documentation panel for details.\n" +
                    "SELECT u.name AS name, o.name AS organisation\n" +
                    "FROM appuser AS u\n" +
                    "JOIN organisation AS o ON u.organisation_id = o.id\n" +
                    "WHERE u.deleted = FALSE AND o.deleted = FALSE\n" +
                    "ORDER BY u.name"
        });
    }
    $scope.result = {};
    $scope.error = null;
    $scope.settings = CustomQuerySettings;
    $scope.CustomQuery = CustomQuery;
    $scope.edit = Editor('query', $scope, {});
    if (!$scope.query.id)
        $scope.edit.edit();

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/2/custom/' + model.id);
    });

    $scope.activeModel = null;
    $scope.$watch('edit.model', function(model) {
        $scope.activeModel = model || $scope.query;
    });
    $scope.$watchGroup(['activeModel.text', 'settings.autorun'], function() {
        if (!$scope.settings.autorun)
            return;
        $scope.autorun();
    });
    $scope.autorun = Enqueue(function() {
        if (!$scope.activeModel || !$scope.settings.autorun)
            return;
        $scope.execute($scope.activeModel.text);
    }, 1000);

    $scope.execute = function(text) {
        var url = '/report/custom_query/preview.json'
        var config = {
            params: {
                limit: $scope.settings.limit,
                wall_time: $scope.settings.wall_time,
            },
        };
        return $http.post(url, text, config).then(
            function success(response) {
                $scope.result = angular.fromJson(response.data);
                var message = "Query finished";
                if (response.headers('Operation-Details'))
                    message += ': ' + response.headers('Operation-Details');
                Notifications.set('query', 'info', message, 5000);
                $scope.error = null;
            },
            function failure(response) {
                $scope.result = null;
                if (response.headers) {
                    var details = response.headers('Operation-Details');
                    if (/statement timeout/.exec(details)) {
                        $scope.error = "Query took too long to run.";
                    } else {
                        $scope.error = details;
                    }
                    return;
                }
                $scope.error = response.statusText;
            }
        );
    };

    $scope.download = function(query, file_type) {
        var fileName = 'custom_query.' + file_type;
        var url = '/report/custom_query/' + query.id + '/' + fileName;
        return download(fileName, url, {}).then(
            function success(response) {
                var message = "Query finished";
                if (response.headers('Operation-Details'))
                    message += ': ' + response.headers('Operation-Details');
                Notifications.set('query', 'info', message, 5000);
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.format = function(query) {
        return $http.post('/report/custom_query/reformat.sql', query.text).then(
            function success(response) {
                query.text = response.data;
                Notifications.set('query', 'info', "Formatted", 5000);
                return query.text;
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.autoName = function(query) {
        return $http.post('/report/custom_query/identifiers.json', query.text).then(
            function success(response) {
                query.title = response.data.autoName;
                Notifications.set('query', 'info', "Generated name", 5000);
                return query.title;
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.colClass = function($index) {
        var col = $scope.result.cols[$index];
        if (col.richType == 'int' || col.richType == 'float')
            return 'numeric';
        else if (col.richType == 'uuid')
            return 'med-truncated';
        else if (col.richType == 'text')
            return 'str-wrap';
        else if (col.richType == 'json')
            return 'pre-wrap';
        else if (col.type == 'date')
            return 'date';
        else
            return null;
    };
    $scope.colRichType = function($index) {
        var col = $scope.result.cols[$index];
        return col.richType;
    };

    $scope.checkRole = Authz({'custom_query': $scope.query});

    hotkeys.bindTo($scope)
        .add({
            combo: ['ctrl+enter'],
            description: "Execute query",
            allowIn: ['TEXTAREA'],
            callback: function(event, hotkey) {
                $scope.execute($scope.query);
            }
        });
})


.controller('CustomListCtrl',
        function($scope, CustomQuery, $routeParams, Authz) {

    $scope.checkRole = Authz({});

    $scope.search = {
        term: $routeParams.initialTerm || "",
        deleted: false,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        CustomQuery.query(search).$promise.then(function(customQueries) {
            $scope.customQueries = customQueries;
        });
    }, true);

})

;
