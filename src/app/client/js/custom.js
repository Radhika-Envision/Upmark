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
        wall_time: 2.0,
    };
})


.controller('CustomCtrl',
            function($scope, $http, Notifications, hotkeys, routeData,
                download, CustomQuery, $q, Editor, Authz, SurveyGroup, Program,
                Organisation, User, Survey, QuestionNode, Measure, Submission,
                $location, CustomQuerySettings, Enqueue, Structure) {

    // Parameterised query stuff
    $scope.checkRole = Authz({});
    $scope.parameterDefaults = {};
    $scope.parameters = {};
    $scope.labels = {};
    var parameterPattern = /in {{\w+}}/gi;

    $scope.deleteParameter = {
        surveygroups: function() {
            $scope.surveygroupSearch = null;
            $scope.surveygroups = null;
            $scope.parameters.surveygroup = [];
            $scope.activeParameters.delete('surveygroups')
        },
        organisations: function() {
          $scope.orgSearch = null;
          $scope.organisations = null;
          $scope.parameters.organisations = [];
          $scope.activeParameters.delete('organisations')
        },
        users: function() {
          $scope.userSearch = null;
          $scope.users = null;
          $scope.parameters.users = [];
          $scope.activeParameters.delete('users')
        },
        programs: function() {
            $scope.programSearch = null;
            $scope.programs = null;
            $scope.parameters.programs = [];
            $scope.activeParameters.delete('programs')
        },
        surveys: function() {
            $scope.surveySearch = null;
            $scope.surveys = null;
            $scope.parameters.surveys = [];
            $scope.activeParameters.delete('surveys')
        },
        submissions: function() {
            $scope.submissionSearch = null;
            $scope.submissions = null;
            $scope.parameters.submissions = [];
            $scope.activeParameters.delete('submissions')
        },
        categories: function() {
            $scope.categorySearch = null;
            $scope.categories = null;
            $scope.parameters.categories = [];
            $scope.activeParameters.delete('categories')
        },
        measures: function() {
            $scope.measureSearch = null;
            $scope.measures = null;
            $scope.parameters.measures = [];
            $scope.activeParameters.delete('measures')
        },
    };
    $scope.addParameter = {
        surveygroups: function() {
            let addedParameters = new Set();
            addedParameters.add('surveygroups');
            if ($scope.activeParameters.has('surveygroups'))
                return addedParameters;

            $scope.labels.surveygroups = {
                "itemsSelected": "surveygroups Selected",
            }

            $scope.selectedSurveyGroupId = function() {
                if ($scope.parameters && $scope.parameters.surveygroup) {
                    let surveygroup = $scope.parameters.surveygroup;
                    if (surveygroup.length > 0)
                        return surveygroup[0].id;
                }

                return null;
            };

            $scope.surveygroupSearch = {
                term: "",
                deleted: false,
            };
            $scope.parameterDefaults.surveygroups = [];
            $scope.activeParameters.add('surveygroups')

            return addedParameters;
        }
    }
    $scope.addParameter.organisations = function() {
        let addedParameters = new Set();
        addedParameters.add('organisations');
        this.surveygroups().forEach(function(dependency) {
            addedParameters.add(dependency)
        });

        if ($scope.activeParameters.has('organisations'))
            return addedParameters;

        $scope.labels.organisations = {
            "itemsSelected": "Organisations Selected",
        }

        $scope.orgSearch = {
            term: "",
            deleted: false,
            surveyGroupId: $scope.selectedSurveyGroupId(),
        };

        let search = {
            term: "",
            deleted: false,
            surveyGroupId: null,
        };
        Organisation.query(search).$promise.then(
            function success(organisations) {
                $scope.parameterDefaults.organisations = organisations;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
        $scope.activeParameters.add('organisations')

        return addedParameters;
    }
    $scope.addParameter.users = function() {
        let addedParameters = new Set();
        addedParameters.add('users');
        this.surveygroups().forEach(function(dependency) {
            addedParameters.add(dependency)
        });

        if ($scope.activeParameters.has('users'))
            return addedParameters;

        $scope.labels.users = {
            "itemsSelected": "Users Selected",
        }

        $scope.userSearch = {
            term: "",
            deleted: false,
            surveyGroupId: $scope.selectedSurveyGroupId(),
        };

        let search = {
            term: "",
            deleted: false,
            surveyGroupId: null,
        };
        User.query(search).$promise.then(
            function success(users) {
                $scope.parameterDefaults.users = users;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
        $scope.activeParameters.add('users')

        return addedParameters;
    }
    $scope.addParameter.programs = function() {
        let addedParameters = new Set();
        addedParameters.add('programs');
        this.surveygroups().forEach(function(dependency) {
            addedParameters.add(dependency)
        });

        if ($scope.activeParameters.has('programs'))
            return addedParameters;

        $scope.labels.programs = {
            "itemsSelected": "Programs Selected",
        }

        $scope.selectedProgramId = function() {
            if ($scope.parameters && $scope.parameters.programs) {
                let programs = $scope.parameters.programs;
                if (programs.length == 1)
                    return programs[0].id;
            }

            return null;
        };

        $scope.programSearch = {
            term: "",
            deleted: false,
            surveyGroupId: $scope.selectedSurveyGroupId(),
        };

        let search = {
            term: "",
            deleted: false,
            surveyGroupId: null,
        };
        Program.query(search).$promise.then(
            function success(programs) {
                $scope.parameterDefaults.programs = programs;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
        $scope.activeParameters.add('programs')

        return addedParameters;
    };
    $scope.addParameter.surveys = function() {
        let addedParameters = new Set();
        addedParameters.add('surveys');
        this.surveygroups().forEach(function(dependency) {
            addedParameters.add(dependency)
        });
        this.programs().forEach(function(dependency) {
            addedParameters.add(dependency)
        });

        if ($scope.activeParameters.has('surveys'))
            return addedParameters;

        $scope.selectedSurveyId = function() {
            if ($scope.parameters && $scope.parameters.surveys) {
                let surveys = $scope.parameters.surveys;
                if (surveys.length == 1)
                    return surveys[0].id;
            }

            return null;
        };

        $scope.labels.surveys = {
            "itemsSelected": "Surveys Selected",
        };

        $scope.surveySearch = {
            term: "",
            deleted: false,
            surveyGroupId: $scope.selectedSurveyGroupId(),
            programId: $scope.selectedProgramId(),
        };
        $scope.parameterDefaults.surveys = [];
        $scope.activeParameters.add('surveys')

        return addedParameters;
    };
    $scope.addParameter.submissions = function() {
        let addedParameters = new Set();
        addedParameters.add('submissions');
        this.surveygroups().forEach(function(dependency) {
            addedParameters.add(dependency)
        });

        if ($scope.activeParameters.has('submissions'))
            return addedParameters;

        $scope.labels.submissions = {
            "itemsSelected": "Submissions Selected",
        };

        $scope.submissionSearch = {
            term: "",
            deleted: false,
            surveyGroupId: $scope.selectedSurveyGroupId(),
        };

        let search = {
            term: "",
            deleted: false,
            surveyGroupId: null,
        };
        Submission.query(search).$promise.then(
            function success(submissions) {
                $scope.parameterDefaults.submissions = submissions;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
        $scope.activeParameters.add('submissions')

        return addedParameters;
    };
    $scope.addParameter.categories = function() {
        let addedParameters = new Set();
        addedParameters.add('categories');
        this.programs().forEach(function(dependency) {
            addedParameters.add(dependency)
        });
        this.surveys().forEach(function(dependency) {
            addedParameters.add(dependency)
        });

        if ($scope.activeParameters.has('categories'))
            return addedParameters;

        $scope.labels.categories = {
            "itemsSelected": "Categories Selected",
        };

        $scope.categorySearch = {
            term: "",
            deleted: false,
            programId: $scope.selectedProgramId(),
            surveyId: $scope.selectedSurveyId(),
            noPage: true,
        };
        $scope.parameterDefaults.categories = [];
        $scope.activeParameters.add('categories')

        return addedParameters;
    };
    $scope.addParameter.measures = function() {
        let addedParameters = new Set();
        addedParameters.add('measures');
        this.programs().forEach(function(dependency) {
            addedParameters.add(dependency)
        });
        this.surveys().forEach(function(dependency) {
            addedParameters.add(dependency)
        });

        if ($scope.activeParameters.has('measures'))
            return addedParameters;

        $scope.labels.measures = {
            "itemsSelected": "Measures Selected",
        };

        $scope.measureSearch = {
            term: "",
            deleted: false,
            programId: $scope.selectedProgramId(),
            surveyId: $scope.selectedSurveyId(),
            noPage: true,
        };
        $scope.parameterDefaults.measures = [];
        $scope.activeParameters.add('measures')

        return addedParameters;
    };

    $scope.surveygroupSearch = null;
    $scope.$watch('surveygroupSearch', function(search) {
        if (!search) {
            return
        }
        SurveyGroup.query(search).$promise.then(
            function success(surveygroups) {
                $scope.surveygroups = surveygroups
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText);
                return $q.reject(details);
            }
        );
    }, true);
    $scope.$watch('parameters.surveygroup', function(group) {
        if (!group) {
            return
        }
        let newGroupId = group.length > 0 ? group[0].id : null;

        if ($scope.orgSearch) {
            $scope.orgSearch.surveyGroupId = newGroupId;
        }

        if ($scope.userSearch) {
            $scope.userSearch.surveyGroupId = newGroupId;
        }

        if ($scope.programSearch) {
            $scope.programSearch.surveyGroupId = newGroupId;
        }

        if ($scope.surveySearch) {
            $scope.surveySearch.surveyGroupId = newGroupId;
        }

        if ($scope.submissionSearch) {
            $scope.submissionSearch.surveyGroupId = newGroupId;
        }

    }, true);

    $scope.orgSearch = null;
    $scope.$watch('orgSearch', function(search) {
        if (!search) {
            return
        }
        Organisation.query(search).$promise.then(
            function success(organisations) {
                $scope.organisations = organisations;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.userSearch = null;
    $scope.$watch('userSearch', function(search) {
        if (!search) {
            return
        }
        User.query(search).$promise.then(
            function success(users) {
                $scope.users = users;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.programSearch = null;
    $scope.$watch('programSearch', function(search) {
        if (!search) {
            return
        }
        Program.query(search).$promise.then(
            function sucess(programs) {
                $scope.programs = programs;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);
    $scope.$watch('parameters.programs', function(programs) {
        if (!$scope.settings.autorun || !programs)
            return;

        if ($scope.surveySearch && programs.length == 1) {
            $scope.surveySearch.programId = programs[0].id;
        } else if ($scope.surveySearch) {
            $scope.surveySearch.programId = null;
        }

        if ($scope.measureSearch && programs.length == 1) {
            $scope.measureSearch.programId = programs[0].id;
        } else if ($scope.measureSearch) {
            $scope.measureSearch.programId = null;
        }

        if ($scope.categorySearch && programs.length == 1) {
            $scope.categorySearch.programId = programs[0].id;
        } else if ($scope.categorySearch) {
            $scope.categorySearch.programId = null;
        }

        $scope.autorun();
    }, true);

    $scope.surveySearch = null;
    $scope.$watch('surveySearch', function(search) {
        if (!search) {
            return
        }

        if (!search.programId) {
            $scope.surveys = $scope.parameterDefaults.surveys;
            return
        }

        Survey.query(search).$promise.then(
            function sucess(surveys) {
                $scope.surveys = surveys;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);
    $scope.$watch('parameters.surveys', function(surveys) {
        if (!$scope.settings.autorun || !surveys)
            return;

        // TODO: What a mess!
        if ($scope.measureSearch && surveys.length == 1) {
            $scope.measureSearch.surveyId = surveys[0].id;
        } else if ($scope.measureSearch) {
            $scope.measureSearch.surveyId = null;
        }

        if ($scope.categorySearch && surveys.length == 1) {
            $scope.categorySearch.surveyId = surveys[0].id;
        } else if ($scope.categorySearch) {
            $scope.categorySearch.surveyId = null;
        }

        $scope.autorun();
    }, true);

    $scope.submissionSearch = null;
    $scope.$watch('submissionSearch', function(search) {
        if (!search) {
            return
        }

        Submission.query(search).$promise.then(
            function sucess(submissions) {
                $scope.submissions = submissions;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.categorySearch = null;
    $scope.$watch('categorySearch', function(search) {
        if (!search) {
            return
        }

        if (!search.programId || !search.surveyId) {
            $scope.categories = $scope.parameterDefaults.categories;
            return
        }

        QuestionNode.query(search).$promise.then(
            function sucess(categories) {
                categories.forEach(function(category, categoryIndex, categoryArray) {
                    category.lineage = getLineage(category);
                    category.displayProp = getDisplayProp(category);
                    categoryArray[categoryIndex] = category;
                })
                $scope.categories = categories.sort(sortByLineage);
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);
    $scope.$watch('parameters.categories', function(categories) {
        if (!$scope.settings.autorun || !categories)
            return;

        if ($scope.measureSearch && categories.length == 1) {
            $scope.measureSearch.qnodeId = categories[0].id;
        } else if ($scope.measureSearch) {
            $scope.measureSearch.qnodeId = null;
        }

        $scope.autorun();
    });

    $scope.measureSearch = null;
    $scope.$watch('measureSearch', function(search) {
        if (!search) {
            return
        }

        if (!search.programId || !search.surveyId) {
            $scope.measures = $scope.parameterDefaults.measures;
            return
        }

        Measure.query(search).$promise.then(
            function sucess(measures) {
                measures.forEach(function(measure, measureIndex, measureArray) {
                    measure.lineage = getLineage(measure);
                    measure.displayProp = getDisplayProp(measure);
                    measureArray[measureIndex] = measure;
                })
                $scope.measures = measures.sort(sortByLineage);
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.$watchGroup(['parameters.submissions', 'parameters.organisations',
        'parameters.measures', 'parameters.users'],
    function(parameter) {
        if (!$scope.settings.autorun || !parameter)
            return;
        $scope.autorun();
    }, true);

    // Functions for dealing with entities with lineage properties.
    var getLineage = function(entity) {
        let hstack = Structure(entity).hstack;
        let lineage = hstack[hstack.length - 1].lineage;

        if (lineage[lineage.length - 1] == '.')
            lineage = lineage.slice(0, -1);

        return lineage
    }
    var getDisplayProp = function(entity) {
        return entity.lineage + ' ' + entity.title;
    }
    var zeroPad = function(number, width) {
        number = number + '';
        let padded = number.width >= width ?
          number : new Array(width - number.length + 1).join('0') + number;

        return padded;
    }
    var padLineage = function(lineage, padWidth) {
        let splitted = lineage.split('.');

        let pad = function(n) {
            return zeroPad(n, padWidth);
        }

        return splitted.map(pad).join('.')
    }
    var sortByLineage = function(entity1, entity2) {
        let padWidth = 5; // Assume a lineage number is never > 10000
        let lineage1 = padLineage(entity1.lineage.slice(), padWidth);
        let lineage2 = padLineage(entity2.lineage.slice(), padWidth);

        if (lineage1 < lineage2)
            return -1;

        if (lineage1 > lineage2)
            return 1;

        return 0;
    }

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
        $location.url('/3/custom/' + model.id);
    });

    $scope.activeModel = null;
    $scope.$watch('edit.model', function(model) {
        $scope.activeModel = model || $scope.query;
    });

    $scope.activeParameters = new Set();
    var hasParameters = function() {
        if ($scope.activeModel) {
            // Search query text for parameters
            var match;
            var currentParameters = new Set();
            parameterPattern.lastIndex = 0;
            do {
                match = parameterPattern.exec($scope.activeModel.text)
                if (match) {
                    let parameter = match[0].slice(5, -2).toLowerCase();
                    if ($scope.addParameter.hasOwnProperty(parameter)) {
                        let dependencies = $scope.addParameter[parameter]()
                        currentParameters.add(parameter)
                        dependencies.forEach(function(dependency) {
                            currentParameters.add(dependency)
                        })
                    } else {
                        $scope.result = null;
                        $scope.error = parameter + " is not a valid parameter";
                        return false
                    }
                }
            } while (match);
        }

        // Deactivate parameters no longer in text
        $scope.activeParameters.forEach(function(param) {
            if (!currentParameters.has(param)) {
                // Parameter should no longer be active.
                $scope.deleteParameter[param]()
            }
        })

        return $scope.activeParameters.size > 0;
    };

    $scope.$watchGroup(['activeModel.text', 'settings.autorun'], function() {
        $scope.error = null;
        $scope.activeModel.isParameterised = hasParameters();
        if (!$scope.settings.autorun)
            return;
        $scope.autorun();
    });

    $scope.setParameters = function(text) {
        let runnable = true;

        text = text.replace(parameterPattern, function(match) {
            let parameter = match.slice(5,-2).toLowerCase();
            let selectedObjects = $scope.parameters[parameter];

            // If nothing has been selected yet or everything has just been
            // de-selected, try the default selection which is usually all.
            if (!selectedObjects || selectedObjects.length < 1)
                selectedObjects = $scope.parameterDefaults[parameter];

            // If no default or default is empty selection, make sure execute
            // won't try to run the query.
            if (!selectedObjects || selectedObjects.length < 1)
                runnable = false;

            // Make a copy so we don't modify parameter objects stored elsewhere
            selectedObjects = selectedObjects.slice();
            selectedObjects.forEach(function(object, index, objectArray) {
                objectArray[index] = object.id;
            })

            let paramValues = "'" + selectedObjects.join("','") + "'";
            return "IN (" + paramValues + ")";
        });

        return {text: text, runnable: runnable}
    }
    $scope.autorun = Enqueue(function() {
        if (!$scope.activeModel || !$scope.settings.autorun || $scope.error) {
            return;
        }

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

        if ($scope.activeModel.isParameterised) {
            let query = $scope.setParameters(text);
            if (!query.runnable) {
                $scope.result = {cols: [], rows: []};
                return
            }
            text = query.text;
        }

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
        var query_data = {};
        if (query.isParameterised) {
            query_data = $scope.setParameters(query.text)
            if (!query_data.runnable) {
                Notifications.set('query', 'error',
                    "Error: Query has parameters that are not set.")
                return;
            }
        }

        var fileName = 'custom_query.' + file_type;
        var url = '/report/custom_query/' + query.id + '/' + fileName;
        return download(fileName, url, query_data).then(
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
