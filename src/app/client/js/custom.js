'use strict';

angular.module('upmark.custom', [
    'ui.select', 'ui.sortable', 'vpac.utils'])


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


.controller('CustomCtrl',
            function($scope, $http, Notifications, hotkeys, routeData,
                download, CustomQuery, $q, Editor, Current, confAuthz,
                $location) {
    $scope.config = routeData.config;
    if (routeData.query) {
        $scope.query = routeData.query;
    } else if (routeData.duplicate) {
        $scope.query = new CustomQuery(routeData.duplicate);
        $scope.query.id = null;
    } else {
        $scope.query = new CustomQuery({
            description: null,
            text:   "-- This example query lists all users.\n" +
                    "-- Replace with your own code.\n" +
                    "SELECT u.name AS name, o.name AS organisation\n" +
                    "FROM appuser AS u\n" +
                    "JOIN organisation AS o ON u.organisation_id = o.id\n" +
                    "WHERE u.deleted = FALSE AND o.deleted = FALSE\n" +
                    "ORDER BY u.name"
        });
    }
    $scope.result = {};
    $scope.execLimit = 20;
    $scope.CustomQuery = CustomQuery;
    $scope.edit = Editor('query', $scope, {});
    if (!$scope.query.id)
        $scope.edit.edit();

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/2/custom/' + model.id);
    });

    $scope.execute = function(query) {
        var url;
        var text;
        if (query.id) {
            url = '/report/custom_query/' + query.id + '/custom_query.json'
            text = null;
        } else {
            url = '/report/custom_query/preview.json'
            text = query;
        }
        var config = {
            params: {limit: $scope.execLimit}
        };
        return $http.post(url, text, config).then(
            function success(response) {
                $scope.result = angular.fromJson(response.data);
                var message = "Query finished";
                if (response.headers('Operation-Details'))
                    message += ': ' + response.headers('Operation-Details');
                Notifications.set('query', 'info', message, 5000);
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + (response.statusText || response));
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

    $scope.checkRole = confAuthz(Current, null);

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
        function($scope, CustomQuery, $routeParams, Current, confAuthz) {

    $scope.checkRole = confAuthz(Current, null);

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
