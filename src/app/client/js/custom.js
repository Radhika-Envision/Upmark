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


.factory('CustomQuery', ['$resource', 'paged', function($resource, paged) {
    return $resource('/custom_query/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
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
        wall_time: 10.0,
    };
})


.controller('CustomCtrl',
            function($scope, $http, Notifications, hotkeys, routeData,
                download, CustomQuery, $q, Editor, Authz, SurveyGroup, Program,
                Organisation, OrgMetaOptions, User, Survey, QuestionNode,
                Measure, Submission, $location, CustomQuerySettings, Enqueue,
                Structure) {

    // Parameterised query stuff
    $scope.parameterDefaults = {};
    $scope.selections = {};
    $scope.labels = {};
    var parameterPattern = /in {{\w+}}/gi;

    function NullDependencies() {
        this.dependencies = new Set();
    }
    NullDependencies.prototype.update = function(paramSelections, paramName) {};

    function SingleSelectionIdDependencies(parameterName) {
        this.parameterName = parameterName;
        this.dependencies = new Set();
    }
    SingleSelectionIdDependencies.prototype = new NullDependencies();
    SingleSelectionIdDependencies.prototype.update = function(paramSelections, paramName) {
          if (!paramSelections)
              return

          let searchName = paramName + 'Search';
          let selectionId =
              paramSelections.length == 1 ? paramSelections[0].id : null;

          let searchConfig = $scope[searchName];
          if (searchConfig) {
              let oldId = searchConfig[this.parameterName];

              if (selectionId != oldId)
                  searchConfig[this.parameterName] = selectionId;
          }
    };

    function DependencyRegister() {
        this.surveygroups = new SingleSelectionIdDependencies('surveyGroupId');
        this.organisations = new SingleSelectionIdDependencies('organisationId');
        this.users = new NullDependencies();
        this.sizes = new NullDependencies();
        this.assettypes = new NullDependencies();
        this.programs = new SingleSelectionIdDependencies('programId');
        this.surveys = new SingleSelectionIdDependencies('surveyId');
        this.submissions = new NullDependencies();
        this.qnodes = new SingleSelectionIdDependencies('qnodeId');
        this.measures = new NullDependencies();
    };
    DependencyRegister.prototype.register = function(paramName, dependency) {
        this[dependency].dependencies.add(paramName)
    };
    DependencyRegister.prototype.unregister = function(paramName, dependency) {
        if (!dependency) {
            for (var param in this) {
                if (this.hasOwnProperty(param)) {
                    this[param].dependencies.delete(paramName)
                }
            }
            return
        }
        this[dependency].delete(paramName)
    };
    var dependencyRegister = new DependencyRegister();

    $scope.$watch('selections', function(selections) {
        for (var parameter in selections) {
            if (selections.hasOwnProperty(parameter)) {
                let parameterSelections = selections[parameter];
                let parameterDependencies = dependencyRegister[parameter];

                if (!parameterDependencies)
                    continue

                parameterDependencies.dependencies.forEach(function(dependency) {
                    parameterDependencies.update(parameterSelections, dependency)
                })
            }
        }
        $scope.autorun()
    }, true);

    $scope.deleteParameter = function(paramName) {
        let searchName = paramName + 'Search';
        $scope[paramName] = null;
        $scope[searchName] = null;
        $scope.selections[paramName] = [];
        $scope.activeParameters.delete(paramName)
        dependencyRegister.unregister(paramName)
    }

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
                if ($scope.selections && $scope.selections.surveygroups) {
                    let surveygroups = $scope.selections.surveygroups;
                    if (surveygroups.length > 0)
                        return surveygroups[0].id;
                }

                return null;
            };

            $scope.surveygroupsSearch = {
                term: "",
                deleted: false,
            };
            $scope.parameterDefaults.surveygroups =
                function(identifier, parameter) {
                    return null;
                };
            $scope.activeParameters.add('surveygroups')

            return addedParameters;
        }
    }

    $scope.addParameter.sizes = function() {
        let dependencies = [];
        let addedParameters = new Set();
        addedParameters.add(['sizes']);

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('sizes', dependency)
        }, this)

        if ($scope.activeParameters.has('sizes'))
            return addedParameters;

        $scope.labels.sizes = {
            "itemsSelected": "Sizes selected",
        };

        $scope.sizes = OrgMetaOptions.sizeTypes.slice();

        let sizes = $scope.sizes.slice();
        sizes.forEach(function(object, index, objectArray) {
            objectArray[index] = object.name;
        })

        $scope.parameterDefaults.sizes =
            function(identifier, parameter) {
                let text = '(' + identifier + " IN ('" + sizes.join("','") + "') OR " + identifier + " IS NULL)";
                return text;
            };

        $scope.activeParameters.add('sizes')

        return addedParameters;
    }

    $scope.addParameter.assettypes = function() {
        let dependencies = [];
        let addedParameters = new Set();
        addedParameters.add(['assettypes']);

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('assettypes', dependency)
        }, this)

        if ($scope.activeParameters.has('assettypes'))
            return addedParameters;

        $scope.labels.assettypes = {
            "itemsSelected": "Asset Types selected",
        };

        $scope.assettypes = OrgMetaOptions.assetTypes.slice();

        let assettypes = $scope.assettypes.slice();
        assettypes.forEach(function(object, index, objectArray) {
            objectArray[index] = object.name;
        })

        $scope.parameterDefaults.assettypes =
            function(identifier, parameter) {
                let text = '(' + identifier + " && ('{" + assettypes.join(",") + "}') OR " + identifier + " IS NULL OR " + identifier + " = '{}')";
                return text;
            };

        $scope.activeParameters.add('assettypes')

        return addedParameters;
    }

    $scope.addParameter.organisations = function() {
        let dependencies = ['surveygroups'];
        let addedParameters = new Set();
        addedParameters.add('organisations');

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('organisations', dependency)
        }, this)

        if ($scope.activeParameters.has('organisations'))
            return addedParameters;

        $scope.labels.organisations = {
            "itemsSelected": "Organisations Selected",
        }

        $scope.selectedOrganisationId = function() {
            if ($scope.selections && $scope.selections.organisations) {
                let organisations = $scope.selections.organisations;
                if (organisations.length == 1)
                    return organisations[0].id;
            }

            return null;
        };

        $scope.organisationsSearch = {
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
                organisations.forEach(function(org, index, objectArray) {
                    objectArray[index] = org.id;
                })

                $scope.parameterDefaults.organisations =
                    function(identifier, parameter) {
                        let text = identifier + " IN ('" + organisations.join("','") + "')";
                        return text;
                    };

                $scope.autorun()
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
        let dependencies = ['surveygroups', 'organisations'];
        let addedParameters = new Set();
        addedParameters.add('users');

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('users', dependency)
        }, this)

        if ($scope.activeParameters.has('users'))
            return addedParameters;

        $scope.labels.users = {
            "itemsSelected": "Users Selected",
        }

        $scope.usersSearch = {
            term: "",
            deleted: false,
            surveyGroupId: $scope.selectedSurveyGroupId(),
            organisationId: $scope.selectedOrganisationId(),
        };

        let search = {
            term: "",
            deleted: false,
            surveyGroupId: null,
            organisationId: null,
        };
        User.query(search).$promise.then(
            function success(users) {
                users.forEach(function(user, index, objectArray) {
                    objectArray[index] = user.id;
                })

                $scope.parameterDefaults.users =
                    function(identifier, parameter) {
                        let text = identifier + " IN ('" + users.join("','") + "')";
                        return text;
                    };

                $scope.autorun()
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
        let dependencies = ['surveygroups'];
        let addedParameters = new Set();
        addedParameters.add('programs');

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('programs', dependency)
        }, this)

        if ($scope.activeParameters.has('programs'))
            return addedParameters;

        $scope.labels.programs = {
            "itemsSelected": "Programs Selected",
        }

        $scope.selectedProgramId = function() {
            if ($scope.selections && $scope.selections.programs) {
                let programs = $scope.selections.programs;
                if (programs.length == 1)
                    return programs[0].id;
            }

            return null;
        };

        $scope.programsSearch = {
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
                programs.forEach(function(program, index, objectArray) {
                    objectArray[index] = program.id;
                })

                $scope.parameterDefaults.programs =
                    function(identifier, parameter) {
                        let text = identifier + " IN ('" + programs.join("','") + "')";
                        return text;
                    };

                $scope.autorun()
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
        let dependencies = ['surveygroups', 'programs'];
        let addedParameters = new Set();
        addedParameters.add('surveys');

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('surveys', dependency)
        }, this)

        if ($scope.activeParameters.has('surveys'))
            return addedParameters;

        $scope.selectedSurveyId = function() {
            if ($scope.selections && $scope.selections.surveys) {
                let surveys = $scope.selections.surveys;
                if (surveys.length == 1)
                    return surveys[0].id;
            }

            return null;
        };

        $scope.labels.surveys = {
            "itemsSelected": "Surveys Selected",
        };

        $scope.surveysSearch = {
            term: "",
            deleted: false,
            surveyGroupId: $scope.selectedSurveyGroupId(),
            programId: $scope.selectedProgramId(),
        };
        $scope.parameterDefaults.surveys =
            function(identifier, parameter) {
                return null;
            };

        $scope.activeParameters.add('surveys')

        return addedParameters;
    };

    $scope.addParameter.submissions = function() {
        let dependencies = ['organisations', 'programs', 'surveys'];
        let addedParameters = new Set();
        addedParameters.add('submissions');

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('submissions', dependency)
        }, this)

        if ($scope.activeParameters.has('submissions'))
            return addedParameters;

        $scope.labels.submissions = {
            "itemsSelected": "Submissions Selected",
        };

        $scope.submissionsSearch = {
            term: "",
            deleted: false,
            organisationId: $scope.selectedOrganisationId(),
            programId: $scope.selectedProgramId(),
            surveyId: $scope.selectedSurveyId(),
        };

        let search = {
            term: "",
            deleted: false,
            organisationId: null,
            programId: null,
            surveyId: null,
        };
        Submission.query(search).$promise.then(
            function success(submissions) {
                submissions.forEach(function(submission, index, objectArray) {
                    objectArray[index] = submission.id;
                })

                $scope.parameterDefaults.submissions =
                    function(identifier, parameter) {
                        let text = identifier + " IN ('" + submissions.join("','") + "')";
                        return text;
                    };

                $scope.autorun()
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

    $scope.addParameter.qnodes = function() {
        let dependencies = ['programs', 'surveys'];
        let addedParameters = new Set();
        addedParameters.add('qnodes');

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('qnodes', dependency)
        }, this)

        if ($scope.activeParameters.has('qnodes'))
            return addedParameters;

        $scope.labels.qnodes = {
            "itemsSelected": "qnodes Selected",
        };

        $scope.qnodesSearch = {
            term: "",
            deleted: false,
            programId: $scope.selectedProgramId(),
            surveyId: $scope.selectedSurveyId(),
            noPage: true,
        };
        $scope.parameterDefaults.qnodes =
            function(identifier, parameter) {
                return null;
            };

        $scope.activeParameters.add('qnodes')

        return addedParameters;
    };

    $scope.addParameter.measures = function() {
        let dependencies = ['programs', 'surveys', 'qnodes'];
        let addedParameters = new Set();
        addedParameters.add('measures');

        dependencies.forEach(function(dependency) {
            this[dependency]().forEach(function(addedDependency) {
                addedParameters.add(addedDependency)
            })
            dependencyRegister.register('measures', dependency)
        }, this)

        if ($scope.activeParameters.has('measures'))
            return addedParameters;

        $scope.labels.measures = {
            "itemsSelected": "Measures Selected",
        };

        $scope.measuresSearch = {
            term: "",
            deleted: false,
            programId: $scope.selectedProgramId(),
            surveyId: $scope.selectedSurveyId(),
            noPage: true,
        };
        $scope.parameterDefaults.measures =
            function(identifier, parameter) {
                return null;
            };
        $scope.activeParameters.add('measures')

        return addedParameters;
    };

    $scope.surveygroupsSearch = null;
    $scope.$watch('surveygroupsSearch', function(search) {
        if (!search)
            return

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


    var selectionTestFactory = function(selection) {
        var isSelected = function(entity) {
            return entity.id == selection.id;
        }

        return isSelected;
    }

    var maintainSelections = function(entityName, newEntities) {
        let currentSelections = $scope.selections[entityName];
        if (currentSelections && currentSelections.length > 0) {
            let selectionsToKeep = [];
            currentSelections.forEach(function(selection) {
                let selectionTest = selectionTestFactory(selection);
                if (newEntities.some(selectionTest))
                    selectionsToKeep.push(selection)
            })
            $scope.selections[entityName] = selectionsToKeep.slice();
        }
    }

    $scope.organisationsSearch = null;
    $scope.$watch('organisationsSearch', function(search) {
        if (!search)
            return;

        Organisation.query(search).$promise.then(
            function success(organisations) {
                maintainSelections('organisations', organisations)
                $scope.organisations = organisations;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.usersSearch = null;
    $scope.$watch('usersSearch', function(search) {
        if (!search)
            return;

        User.query(search).$promise.then(
            function success(users) {
                maintainSelections('users', users)
                $scope.users = users;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.programsSearch = null;
    $scope.$watch('programsSearch', function(search) {
        if (!search)
            return;

        Program.query(search).$promise.then(
            function sucess(programs) {
                maintainSelections('programs', programs)
                $scope.programs = programs;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.surveysSearch = null;
    $scope.$watch('surveysSearch', function(search) {
        if (!search)
            return;

        if (!search.programId) {
            $scope.surveys = $scope.parameterDefaults.surveys;
            maintainSelections('surveys', $scope.surveys);
            $scope.labels.surveys = {
                "select": "Surveys: Please select a single program first",
            };
            return;
        }

        Survey.query(search).$promise.then(
            function sucess(surveys) {
                maintainSelections('surveys', surveys)
                $scope.surveys = surveys;
                $scope.labels.surveys = {
                    "select": "Surveys",
                };
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.submissionsSearch = null;
    $scope.$watch('submissionsSearch', function(search) {
        if (!search)
            return;

        Submission.query(search).$promise.then(
            function sucess(submissions) {
                maintainSelections('submissions', submissions)
                $scope.submissions = submissions;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.qnodesSearch = null;
    $scope.$watch('qnodesSearch', function(search) {
        if (!search)
            return;

        if (!search.programId || !search.surveyId) {
            $scope.qnodes = $scope.parameterDefaults.qnodes;
            maintainSelections('qnodes', $scope.qnodes);
            $scope.labels.qnodes = {
                "select": "Categories: Please select a single program and survey first",
            };
            return;
        }

        QuestionNode.query(search).$promise.then(
            function sucess(qnodes) {
                qnodes.forEach(function(qnode, qnodeIndex, qnodeArray) {
                    qnode.lineage = getLineage(qnode);
                    qnode.displayProp = getDisplayProp(qnode);
                    qnodeArray[qnodeIndex] = qnode;
                })
                maintainSelections('qnodes', qnodes)
                $scope.qnodes = qnodes.sort(sortByLineage);
                $scope.labels.qnodes = {
                    "select": "Categories",
                };
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    $scope.measureSearch = null;
    $scope.$watch('measuresSearch', function(search) {
        if (!search)
            return;

        if (!search.programId || !search.surveyId) {
            $scope.measures = $scope.parameterDefaults.measures;
            maintainSelections('measures', $scope.measures);
            $scope.labels.measures = {
                "select": "Measures: Please select a single program and survey first",
            };
            return;
        }

        Measure.query(search).$promise.then(
            function sucess(measures) {
                let helpMessage = '';
                if (search.qnodeId && measures.length < 1) {
                    helpMessage =
                        ": Selected category has no measures but a subcategory might";
                } else {
                    measures.forEach(function(measure, measureIndex, measureArray) {
                        measure.lineage = getLineage(measure);
                        measure.displayProp = getDisplayProp(measure);
                        measureArray[measureIndex] = measure;
                    })
                }
                maintainSelections('measures', measures)
                $scope.measures = measures.sort(sortByLineage);
                $scope.labels.measures = {
                    "select": "Measures" + helpMessage,
                };
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list:" + details.statusText, 10000);
                return $q.reject(details);
            }
        );
    }, true);

    // Functions for dealing with entities' lineage properties.
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
                        return {
                            isParameterised: true,
                            isRunnable: false,
                        };
                    }
                }
            } while (match);
        }

        // De-activate parameters no longer in query text
        $scope.activeParameters.forEach(function(param) {
            if (!currentParameters.has(param)) {
                $scope.deleteParameter(param)
            }
        })

        return {
            isParameterised: $scope.activeParameters.size > 0,
            isRunnable: true,
        };
    };

    $scope.$watchGroup(['activeModel.text', 'settings.autorun'], function() {
        $scope.error = null;
        let parameterisation = hasParameters();
        $scope.activeModel.isParameterised = parameterisation.isParameterised;

        if (parameterisation.isRunnable)
            $scope.autorun();
    });

    $scope.setParameters = function(text) {
        let runnable = true;
        var statementPattern = /\w+\.\w+ in {{\w+}}/gi;

        text = text.replace(statementPattern, function(match) {
            let splitted = match.split(' ');
            let parameterName = splitted[2].slice(2, -2).toLowerCase();
            let identifier = splitted[0];
            let selectedObjects = $scope.selections[parameterName];

            // If nothing has been selected yet or everything has just been
            // de-selected, try the default selection which is usually all.
            if (!selectedObjects || selectedObjects.length < 1) {
                let defaultFunction = $scope.parameterDefaults[parameterName];
                let defaultText = defaultFunction(identifier, parameterName);

                // If no default, ensure execute doesn't try to run the query.
                if (!defaultText) {
                    runnable = false;
                    defaultText = match;
                }

                return defaultText;
            }

            // Make a copy so we don't modify parameter objects stored elsewhere
            selectedObjects = selectedObjects.slice();
            selectedObjects.forEach(function(object, index, objectArray) {
                if (object.id) {
                    objectArray[index] = object.id;
                } else {
                    objectArray[index] = object.name;
                }
            })

            let paramValues;
            if (parameterName != 'assettypes') {
                paramValues = "'" + selectedObjects.join("','") + "'";
                return identifier + " IN (" + paramValues + ")";
            } else {
                paramValues = "'{" + selectedObjects.join(",") + "}'";
                return identifier + " && (" + paramValues + ")";
            }
        });

        return {text: text, runnable: runnable}
    }

    $scope.autorun = Enqueue(function() {
        if (!$scope.activeModel || !$scope.settings.autorun) {
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
                        $scope.result = {cols: [], rows: []};
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
