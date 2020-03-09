'use strict';

angular.module('upmark.response.type', [
    'ngResource', 'upmark.admin.settings', 'upmark.user', 'upmark.chain'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/response-type/:responseType', {
            templateUrl : 'response_type.html',
            controller : 'ResponseTypeCtrl',
            resolve: {routeData: chainProvider({
                responseType: ['ResponseType', '$route',
                        function(ResponseType, $route) {
                    return ResponseType.get({
                        id: $route.current.params.responseType,
                        programId: $route.current.params.program
                    }).$promise;
                }]
            })}
        })
    ;
})


.factory('responseTypes', function() {

    // These functions are used to calculate scores and validate entered data.
    // NOTE: keep changes made to these classes in sync with those in
    // response_type.py.

    var uniqueStrings = function(ss) {
        var set = {},
            res = [];
        ss.forEach(function(s) {
            if (set.hasOwnProperty(s))
                return;
            set[s] = true;
            res.push(s);
        });
        return res.sort();
    };
    var parse = function(exp) {
        try {
            return exp ? Parser.parse(exp) : null;
        } catch (e) {
            if (/parse error/.exec(e))
                console.log("Failed to parse expression '" + exp + "': " + e)
            return null;
        }
    };
    var refs = function(cExp) {
        return cExp ? cExp.variables() : [];
    };




    /*function ResponseType(name, partsDef, formula, merge) {
        this.name = name;
        this.parts = partsDef && partsDef.map(responsePart) || [];s
        this.formula = parse(formula);
        var parts =angular.copy(this.parts);
        var gormular=angular.copy(this.formula);
        if (merge) {
            parts =angular.copy( merge.parts && merge.parts.map(responsePart) || []);
            formula=angular.copy(parse(merge.formula));
        }

        this.declaredVars = uniqueStrings(
            parts.reduce(function(prev, part) {
                return prev.concat(part.declaredVars);
            }, []));
        this.freeVars = uniqueStrings(
            parts.reduce(function(prev, part) {
                return prev.concat(part.freeVars);
            }, refs(formula)));
        this.unboundVars = uniqueStrings(
            this.freeVars.filter(function(fv) {
                return this.declaredVars.indexOf(fv) < 0;
            }, this));
    };*/

    function ResponseType(name, partsDef, formula, merge) {
        this.name = name;
        
        if (merge) {
            //this.parts = merge.parts && merge.parts.map(responsePart) || [];
            this.parts = partsDef && partsDef.map(responsePart) || [];
           this.formula=parse(merge.formula);
        }
        else {
            this.parts = partsDef && partsDef.map(responsePart) || [];
            this.formula = parse(formula);
        }
        if (this.formula && this.formula.functions) {
            this.formula.functions.median = function(...arr) {
                const mid = Math.floor(arr.length / 2),
                    nums = [...arr].sort((a, b) => a - b);
                return arr.length % 2 !== 0 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
            }
        }
        this.declaredVars = uniqueStrings(
            this.parts.reduce(function(prev, part) {
                return prev.concat(part.declaredVars);
            }, []));
        this.freeVars = uniqueStrings(
            this.parts.reduce(function(prev, part) {
                return prev.concat(part.freeVars);
            }, refs(this.formula)));
        this.unboundVars = uniqueStrings(
            this.freeVars.filter(function(fv) {
                return this.declaredVars.indexOf(fv) < 0;
            }, this));
    };


    
    ResponseType.prototype.zip = function(responseParts) {
        var partPairs = [];
        for (var i = 0; i < this.parts.length; i++) {
            partPairs.push({
                index: i,
                schema: this.parts[i],
                data: responseParts[i],
            });
        }
        return partPairs;
    };
    ResponseType.prototype.score = function(responseParts, scope) {
        if (this.formula)
            return this.formula.evaluate(scope);

        var score = 0.0;
        this.zip(responseParts).forEach(function(part) {
            score += part.schema.score(part.data);
        });
        return score;
    };
    ResponseType.prototype.variables = function(responseParts, ignoreErrors) {
        var scope = {};
        this.zip(responseParts).forEach(function(part) {
            var vars;
            try {
                vars = part.schema.variables(part.data);
            } catch (e) {
                if (!ignoreErrors)
                    throw e;
            }
            angular.merge(scope, vars);
        });
        return scope;
    };
    ResponseType.prototype.humanize_variable = function(field_name) {
        if (field_name == '_raw')
            return 'Raw score';
        if (field_name == '_score')
            return 'Weighted score';
        if (field_name == '_weight')
            return 'Measure weight';
        for (var i = 0; i < this.parts.length; i++) {
            var part = this.parts[i];
            if (field_name != part.name)
                continue;
            if (part.name)
                return 'Part ' + part.name;
            return 'Part ' + i;
        }
        return 'Unknown field ' + field_name;
    };
    ResponseType.prototype.validate = function(responseParts, scope) {
        this.zip(responseParts).forEach(function(part, index) {
            try {
                part.schema.validate(part.data, scope);
            } catch (e) {
                var name;
                if (part.schema.name) {
                    name = '' + part.schema.name;
                } else {
                    if (this.parts.length > 1)
                        name = "Part " + (index + 1);
                    else
                        name = "Response";
                }
                throw name + ": " + e;
            }
        }, this);
    };

    //check responses depend on choose by detang on 17/09/2019
    ResponseType.prototype.validateResponses = function(responseParts, scope) {
        this.zip(responseParts).forEach(function(part, index) {
            try {
                part.schema.validate(part.data, scope);
            } catch (e) {
              //empty response if choose make it invalid 
              delete part.data.index;
              delete part.data.note;
            }
        }, this);
    };


    ResponseType.prototype.calculate_score = function(responseParts) {
        if (!responseParts || responseParts.length != this.parts.length)
            throw "Response is incomplete.";

        var scope = this.variables(responseParts);
        this.validate(responseParts, scope);
        return this.score(responseParts, scope);
    };


    function responsePart(pDef) {
        if (pDef.type == 'multiple_choice')
            return new MultipleChoice(pDef);
        else
            return new Numerical(pDef);
    };


    function ResponsePart(pDef) {
        this.id = pDef.id;
        this.name = pDef.name;
        this.type = pDef.type;
        this.description = pDef.description;
        if (pDef.submeasure) {
            this.submeasure=pDef.submeasure;
        }
    };


    function MultipleChoice(pDef) {
        ResponsePart.call(this, pDef);
        this.options = pDef.options.map(function(oDef) {
            return new ResponseOption(oDef);
        });
        this.declaredVars = this.id ? [this.id, this.id + '__i'] : [];
        this.freeVars = uniqueStrings(
            this.options.reduce(function(prev, option) {
                return prev.concat(option.freeVars);
            }, []));
    };
    MultipleChoice.prototype = Object.create(ResponsePart.prototype);
    MultipleChoice.prototype.score = function(part) {
        var option = this.options[part.index];
        return option.score;
    };
    MultipleChoice.prototype.variables = function(part) {
        var variables = {};
        if (this.id) {
            variables[this.id] = this.options[part.index].score;
            variables[this.id + '__i'] = part.index;
        }
        return variables;
    };
    MultipleChoice.prototype.validate = function(part, scope) {
        if (part.index == null)
            throw "Choose an option";
        var option = this.options[part.index];
        if (!option.available(scope))
            throw "Can't select \"" + option.name + "\"";
    };


    function ResponseOption(oDef) {
        this.score = oDef.score;
        this.name = oDef.name;
        this.description = oDef.description;
        this.predicate = parse(oDef['if']);
        this.freeVars = refs(this.predicate);
    };
    ResponseOption.prototype.available = function(scope) {
        if (!this.predicate)
            return true;
        try {
            return Boolean(this.predicate.evaluate(scope));
        } catch (e) {
            return false;
        }
    };


    function Numerical(pDef) {
        ResponsePart.call(this, pDef);
        this.lowerExp = parse(pDef.lower);
        this.upperExp = parse(pDef.upper);
        this.declaredVars = this.id ? [this.id] : [];
        this.freeVars = uniqueStrings(
            refs(this.lowerExp).concat(refs(this.upperExp)));
    };
    Numerical.prototype = Object.create(ResponsePart.prototype);
    Numerical.prototype.score = function(part) {
        return part.value;
    };
    Numerical.prototype.variables = function(part) {
        var variables = {};
        if (this.id)
            variables[this.id] = part.value;
        return variables;
    };
    Numerical.prototype.lower = function(scope) {
        if (!this.lowerExp)
            return Number.NEGATIVE_INFINITY;
        return this.lowerExp.evaluate(scope);
    };
    Numerical.prototype.upper = function(scope) {
        if (!this.upperExp)
            return Number.POSITIVE_INFINITY;
        return this.upperExp.evaluate(scope);
    };
    Numerical.prototype.validate = function(part, scope) {
        if (part.value == null)
            throw "Please specify a value";
        var score = this.score(part);
        try {
            if (this.lower(scope) > score)
                throw "Must be at least " + this.lower(scope);
            if (this.upper(scope) < score)
                throw "Must be at most " + this.upper(scope);
        } catch (e) {
            throw e;
        }
    };

    return {
        ResponseType: ResponseType,
        MultipleChoice: MultipleChoice,
        Numerical: Numerical,
    };
})


.factory('ResponseType', ['$resource', 'paged', function($resource, paged) {
    var ResponseType = $resource('/response_type/:id.json', {
        id: '@id', programId: '@programId'
    }, {
        get: {
            method: 'GET', cache: false,
            interceptor: {response: function(response) {
                response.resource.title = response.resource.name;
                return response.resource;
            }}
        },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        history: { method: 'GET', url: '/response_type/:id/program.json',
            isArray: true, cache: false }
    });
    ResponseType.prototype.$createOrSave = function(parameters, success, error) {
        if (!this.id)
            return this.$create(parameters, success, error);
        else
            return this.$save(parameters, success, error);
    };
    return ResponseType;
}])


.controller('ResponseTypeCtrl',
        function($scope, Authz, Measure, layout, routeData,
            ResponseType) {

    $scope.layout = layout;
    $scope.checkRole = Authz({});
    $scope.responseType = routeData.responseType;
    $scope.ResponseType = ResponseType;
})


.directive('responseTypeEditor', function() {
    return {
        restrict: 'A',
        scope: {
            rt: '=responseTypeEditor',
            weight: '=',
            isBound: '=',
        },
        templateUrl: 'response_type_editor.html',
        controller: function($scope, Numbers, responseTypes, $timeout, Enqueue) {
            //$scope.$on("remove-responseType",function(){
            //    $scope.$broadcast("remove-responseType");
            //})
            $scope.$watch('rt', function(rt) {
                $scope.rtEdit = {
                    rt: rt,
                    responseType: null,
                    externs: {},
                    response: {
                        responseParts: [],
                        comment: ''
                    },
                    activeTab: 'details',
                };
            });
            $scope.addPart = function(rt, $event) {
                var ids = {};
                for (var i = 0; i < rt.parts.length; i++) {
                    ids[rt.parts[i].id] = true;
                }
                var id;
                for (var i = 0; i <= rt.parts.length; i++) {
                    id = Numbers.idOf(i);
                    if (!ids[id])
                        break;
                }
                var part = {
                    id: id,
                    name: 'Response part ' + id.toUpperCase(),
                };
                $scope.setType(part, 'multiple_choice');
                rt.parts.push(part);
                $scope.updateFormula(rt);

                $timeout(function() {
                    $scope.rtEdit.activeTab = rt.parts.indexOf(part);
                });
            };
            $scope.setType = function(part, type) {
                part.type = type;
                if (type == 'multiple_choice' && !part.options) {
                    part.options = [
                        {score: 0, name: 'No', 'if': null},
                        {score: 1, name: 'Yes', 'if': null}
                        //{score: 0.5, name: 'Yes', 'if': null}
                    ];
                }
            };
            $scope.addOption = function(part) {
                part.options.push({
                    score: 0,
                    //score: part.options.length / (part.options.length + 1),
                    name: 'Option ' + (part.options.length + 1)
                })
            };
            $scope.updateFormula = function(rt) {
                if (rt.parts.length <= 1) {
                    rt.formula = null;
                    return;
                }
                var formula = "";
                for (var i = 0; i < rt.parts.length; i++) {
                    var part = rt.parts[i];
                    if (i > 0)
                        formula += " + ";
                    if (part.id)
                        formula += part.id;
                    else
                        formula += "?";
                }
                rt.formula = formula;
            };
            $scope.remove = function(rt, list, item) {
                var i = list.indexOf(item);
                if (i < 0)
                    return;
                list.splice(i, 1);
                if (item.options)
                    $scope.updateFormula(rt);
            };

            var rtDefChanged = Enqueue(function() {
                var rtDef = $scope.rtEdit.rt;
                if (!rtDef) {
                    $scope.rtEdit.responseType = null;
                    return;
                }
                //var merge=null;
                //if ($scope.$root && $scope.$root.merge) {
                //    merge=$scope.$root.merge;
                //}
                $scope.rtEdit.responseType = new responseTypes.ResponseType(
                    rtDef.name, rtDef.parts, rtDef.formula);
            }, 0, $scope);
            $scope.$watch('rtEdit.rt', rtDefChanged);
            $scope.$watch('rtEdit.rt', rtDefChanged, true);

            $scope.partTypes = [
                {name: 'multiple_choice', desc: 'Multiple choice'},
                {name: 'numerical', desc: 'Numerical'},
            ];
            $scope.partTypeMap = $scope.partTypes.reduce(function(ts, t){
                ts[t.name] = t.desc;
                return ts;
            }, {});

            $scope.$watchGroup(['rt.nMeasures', 'isBound'], function(vars) {
                var nMeasures = vars[0];
                if ($scope.isBound)
                    $scope.nMeasures = nMeasures - 1;
                else
                    $scope.nMeasures = nMeasures;
            });
        },
        link: function(scope, elem, attrs) {
        },
    };
})


.directive('responseTypesEditor', function() {
    return {
        restrict: 'A',
        scope: {
            rt: '=responseTypesEditor',
            indexSub:'=indexSub',
            formula:'=',
            weight: '=',
            isBound: '=',
        },
        templateUrl: 'response_types_editor.html',
        controller:  function($scope, Numbers, responseTypes, $timeout, Enqueue, $rootScope) {
            if ($scope.indexSub || $scope.indexSub==0) {
                if ($rootScope.rts && $rootScope.rts[$scope.indexSub]) {
                    $rootScope.rts[$scope.indexSub]=$scope;
                    //$rootScope.questions.push($scope);
                }
                else {
                    //$rootScope.questions=[$scope];
                }
            }
            $scope.$watch('rt', function(rt) {
                $scope.rtEdit = {
                    rt: rt,
                    responseType: null,
                    externs: {},
                    response: {
                        responseParts: [],
                        comment: ''
                    },
                    activeTab: 'details',
                };
            });
            $scope.addPart = function(rt, $event) {
                var ids = {};
                for (var i = 0; i < rt.parts.length; i++) {
                    ids[rt.parts[i].id] = true;
                }
                var id;
                for (var i = 0; i <= rt.parts.length; i++) {
                    id = Numbers.idOf(i);
                    if (!ids[id])
                        break;
                }
                var part = {
                    id: id,
                    name: 'Response part ' + id.toUpperCase(),
                };
                $scope.setType(part, 'multiple_choice');
                rt.parts.push(part);
                $scope.updateFormula(rt);

                $timeout(function() {
                    $scope.rtEdit.activeTab = rt.parts.indexOf(part);
                });
            };
            $scope.setType = function(part, type) {
                part.type = type;
                if (type == 'multiple_choice' && !part.options) {
                    part.options = [
                        {score: 0, name: 'No', 'if': null},
                        {score: 1, name: 'Yes', 'if': null}
                        //{score: 0.5, name: 'Yes', 'if': null}
                    ];
                }
            };
            $scope.addOption = function(part) {
                part.options.push({
                    score: 0,
                    //score: part.options.length / (part.options.length + 1),
                    name: 'Option ' + (part.options.length + 1)
                })
            };
            $scope.updateFormula = function(rt) {
                if (rt.parts.length <= 1) {
                    rt.formula = null;
                    return;
                }
                var formula = "";
                for (var i = 0; i < rt.parts.length; i++) {
                    var part = rt.parts[i];
                    if (i > 0)
                        formula += " + ";
                    if (part.id)
                        formula += part.id;
                    else
                        formula += "?";
                }
                rt.formula = formula;
            };
            $scope.remove = function(rt, list, item) {
                var i = list.indexOf(item);
                if (i < 0)
                    return;
                list.splice(i, 1);
                if (item.options)
                    $scope.updateFormula(rt);
            };

            var rtDefChanged = Enqueue(function() {
                //keep submeasure index
                if ($scope.indexSub)
                   $rootScope.indexSub=$scope.indexSub; 
                var rtDef = $scope.rtEdit.rt;
                if (!rtDef) {
                    $scope.rtEdit.responseType = null;
                    return;
                }
                var mergeParts=[];
                angular.forEach($scope.$root.rts,function(rt,i){
                    if (!angular.equals({}, rt)) {
                       mergeParts=[...mergeParts, ...rt.rtEdit.rt.parts]
                    }
                });
                var merge={parts:mergeParts, formula:$scope.formula};
                $scope.rtEdit.responseType = new responseTypes.ResponseType(
                    rtDef.name, rtDef.parts, rtDef.formula, merge);
                $scope.$emit('response-type-changed');
                angular.forEach($scope.$root.rts,function(s,i){
                    if (!angular.equals({},s)) { 
                        if (s.rtEdit.activeTab == 'preview')               
                            s.rtEdit.activeTab = 'details';
                    }
                })
            }, 0, $scope);
            $scope.$watch('rtEdit.rt', rtDefChanged);
            $scope.$watch('rtEdit.rt', rtDefChanged, true);
            


            /*$scope.$watch('formula',  function(vars) {
                if ($scope.indexSub || $rootScope.indexSub) {
                    return rtDefChanged;
                }
            }, true);*/ 

            $scope.$watch('formula', rtDefChanged);

            $scope.$watch('formula', rtDefChanged, true);





            $scope.partTypes = [
                {name: 'multiple_choice', desc: 'Multiple choice'},
                {name: 'numerical', desc: 'Numerical'},
            ];
            $scope.partTypeMap = $scope.partTypes.reduce(function(ts, t){
                ts[t.name] = t.desc;
                return ts;
            }, {});

            $scope.$watchGroup(['rt.nMeasures', 'isBound'], function(vars) {
                var nMeasures = vars[0];
                if ($scope.isBound)
                    $scope.nMeasures = nMeasures - 1;
                else
                    $scope.nMeasures = nMeasures;
            });

            //$scope.loadFooItems= function(rt, list, item) {
            //    $scope.rtEdit.activeTab = "preview";
               // var i = list.indexOf(item);
                //if (i < 0)
                 //   return;
                //list.splice(i, 1);
                //if (item.options)
                //    $scope.updateFormula(rt);
            //};
            //this.setActiveTab = function() { 
            //    $scope.rtEdit.activeTab = "preview";
            //};
        },
        link: function(scope, elem, attrs) {
            //ngCtrl.setActiveTab();
            //$scope.setActiveTab();
            //var notSetActiveTab=true;
            /*if (scope.$parent.$parent.$parent.$parent.previewList) {
                scope.$parent.$parent.$parent.$parent.previewList.push(scope);
            }
            else {
                scope.$parent.$parent.$parent.$parent.previewList=[scope];
            }*/
             
            scope.setActiveTab = function(tab) { 
                if (scope.$root.indexSub && scope.$root.rts) {
                    var lastRt=0;
                    var unboundVars=[];
                    var indexSub=scope.$root.indexSub;
                    angular.forEach(scope.$root.rts,function(s,i){
                        if (!angular.equals({},s)) {                
                            s.rtEdit.activeTab = tab;
                            if (indexSub != i && s.rtEdit.responseType.unboundVars.length>0) {
                            s.rtEdit.responseType.unboundVars=[];
                        }
                            lastRt=i;
                        }
                    })
                //only display in the last no empty submeasure
                
                    if (indexSub != lastRt && scope.$root.rts[indexSub].rtEdit.responseType.unboundVars.length>0) {
                       unboundVars=angular.copy(scope.$root.rts[indexSub].rtEdit.responseType.unboundVars);
                       scope.$root.rts[indexSub].rtEdit.responseType.unboundVars=[];
                       scope.$root.rts[lastRt].rtEdit.responseType.unboundVars=angular.copy(unboundVars);
                    }

                }
                /*scope.$root.rts[lastRt].rtEdit.responseType.unboundVars=unboundVars;
                //if (setActiveTab) {
                    angular.forEach(scope.$parent.$parent.$parent.$parent.previewList,function(s,i){
                        //if (tab!='')
                           s.rtEdit.activeTab = tab;
                        //else
                        //   s.rtEdit.activeTab = 'details'; 
                    })*/
            }
                
           // };           
            //console.log(elem.controller('responseTypesEditor'));
        },
    };
})

;
