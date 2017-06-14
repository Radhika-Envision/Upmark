'use strict';

angular.module('upmark.custom', [
    'ui.select', 'ui.sortable', 'vpac.utils'])


.controller('CustomCtrl', ['$scope', '$http', 'Notifications', 'samples',
            'hotkeys', 'config', 'download',
            function($scope, $http, Notifications, samples, hotkeys, config,
                download) {
    $scope.config = config;
    $scope.query = samples[0].query;
    $scope.result = {};
    $scope.samples = samples;
    $scope.execLimit = 20;

    $scope.execute = function(query) {
        var config = {
            params: {limit: $scope.execLimit}
        };
        $http.post('/report/custom_query.json', query, config).then(
            function success(response) {
                var message = "Query finished";
                if (response.headers('Operation-Details'))
                    message += ': ' + response.headers('Operation-Details');
                Notifications.set('query', 'info', message, 5000);

                $scope.result = angular.fromJson(response.data);
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.download = function(query, file_type) {
        var fileName = 'custom_query.' + file_type;
        var url = '/report/' + fileName;
        return download(fileName, url, query).then(
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
        $http.post('/report/custom_query/reformat.sql', $scope.query).then(
            function success(response) {
                $scope.query = response.data;
                Notifications.set('query', 'info', "Formatted", 5000);
            },
            function failure(response) {
                Notifications.set('query', 'error',
                    "Error: " + response.statusText);
            }
        );
    };

    $scope.setQuery = function(query) {
        $scope.query = query;
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

    hotkeys.bindTo($scope)
        .add({
            combo: ['ctrl+enter'],
            description: "Execute query",
            allowIn: ['TEXTAREA'],
            callback: function(event, hotkey) {
                $scope.execute($scope.query);
            }
        });
}])

;
