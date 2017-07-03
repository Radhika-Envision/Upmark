'use strict';

angular.module('upmark.admin.settings', [
    'ngResource', 'ngSanitize', 'ui.select', 'ngCookies', 'color.picker',
    'upmark.authz', 'upmark.user', 'upmark.organisation'])


.directive('numericalSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-numerical.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };

            scope.isFinite = isFinite;
        }
    };
})


.directive('stringSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-string.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };
        }
    };
})


.directive('booleanSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-boolean.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };
        }
    };
})


.directive('fileSetting', function($http, $cookies, $q) {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        templateUrl: 'setting-image.html',
        require: '^form',
        link: function(scope, elem, attrs, formCtrl) {
            var getParams = function() {
                var url = '/systemconfig/' + scope.setting.name;
                var xsrfName = $http.defaults.xsrfHeaderName;
                var headers = {};
                headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);
                return {
                    url: url,
                    headers: headers,
                };
            };
            var dropzone;
            var deferred;
            scope.$watch('setting', function(setting) {
                var options = angular.merge({}, getParams(), {
                    maxFilesize: 50,
                    paramName: "file",
                    acceptedFiles: scope.setting.accept,
                    autoProcessQueue: false
                });
                dropzone = new Dropzone(elem.children()[0], options);

                dropzone.on('uploadprogress', function(file, progress) {
                    deferred.notify(progress);
                });

                dropzone.on("success", function(file, response) {
                    deferred.resolve();
                    setting.action = null;
                });

                dropzone.on('addedfile', function(file) {
                    if (dropzone.files.length > 1)
                        dropzone.removeFile(dropzone.files[0]);
                    setting.value = "file.name";
                    setting.action = 'upload';
                    formCtrl.$setDirty();
                    scope.$apply();
                });

                dropzone.on("error", function(file, details, request) {
                    if (request)
                        deferred.reject("Upload failed: " + request.statusText);
                    else
                        deferred.reject("Upload failed: " + details);
                });
            });

            scope.reset = function () {
                dropzone.removeAllFiles();
                scope.setting.action = 'reset';
                formCtrl.$setDirty();
            };

            scope.$on('prepareFormSubmit', function(event, promises) {
                if (scope.setting.action == 'reset') {
                    var options = angular.merge({}, getParams(), {
                        method: 'DELETE',
                    });
                    promises.push($http(options));
                    return;
                }

                if (!dropzone.files.length)
                    return;

                deferred = $q.defer();
                promises.push(deferred.promise);
                dropzone.processQueue();
            });
            scope.$on('$destroy', function() {
                scope = null;
                formCtrl = null;
                dropzone = null;
            });
        }
    };
})


.directive('colourSetting', function() {
    return {
        restrict: 'E',
        scope: {
            setting: '='
        },
        require: '^form',
        templateUrl: 'setting-colour.html',
        link: function(scope, elem, attrs, formCtrl) {
            scope.options = {
                format: 'hex8',
                swatchBootstrap: true,
                case: 'lower',
            };
            scope.reset = function () {
                scope.setting.value = scope.setting.defaultValue;
                formCtrl.$setDirty();
            };
            elem.find('.color-picker-input-wrapper').append(
                elem.find('.input-group-btn'));
        }
    };
})


;
