'use strict';

angular.module('upmark.response', ['ngResource', 'upmark.admin'])


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


    function ResponseType(name, partsDef, formula) {
        this.name = name;
        this.parts = partsDef && partsDef.map(responsePart) || [];
        this.formula = parse(formula);
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


.directive('responseForm', function() {
    return {
        restrict: 'E',
        scope: {
            rt: '=type',
            response: '=model',
            weight_: '=weight',
            readonly: '=',
            hasQuality: '=',
            externs: '=',
            isDummy: '@',
        },
        replace: true,
        templateUrl: 'response_form.html',
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Authz', 'Enqueue',
                function($scope, hotkeys, Authz, Enqueue) {
            $scope.$watch('weight_', function(weight) {
                $scope.weight = weight == null ? 100 : weight;
            });

            $scope.state = {
                variables: null,
                score: 0,
                active: 0
            };

            var recalculate = Enqueue(function() {
                if ($scope.isDummy)
                    return;
                var rt = $scope.rt,
                    partsR = $scope.response.responseParts;

                if (!rt || !partsR) {
                    $scope.state.score = 0;
                    $scope.state.active = 0;
                    $scope.state.message = 'Loading';
                    return;
                }
                rt.parts.forEach(function(part, i) {
                    if (!partsR[i])
                        partsR[i] = {};
                });

                if ($scope.response.notRelevant) {
                    $scope.state.variables = angular.merge({}, $scope.externs);
                    $scope.state.score = 0;
                } else {
                    $scope.state.variables = angular.merge(
                        {}, $scope.externs, rt.variables(partsR, true));
                    try {
                        rt.validate(partsR, $scope.state.variables);
                        $scope.state.score = rt.score(
                            partsR, $scope.state.variables);
                        $scope.state.message = null;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                    }
                }
            }, 0, $scope);
            $scope.$watch('rt', recalculate);
            $scope.$watch('response.responseParts', recalculate, true);
            $scope.$watch('externs', recalculate, true);

            $scope.getPartData = function(partSchema) {
                if ($scope.isDummy)
                    return;
                var i = $scope.rt.parts.indexOf(partSchema);
                return $scope.response.responseParts[i];
            };

            $scope.choose = function(partSchema, option) {
                var partData = $scope.getPartData(partSchema);
                partData.index = partSchema.options.indexOf(option);
                partData.note = option.name;
                var nParts = $scope.rt.parts.length;
                var iPart = $scope.rt.parts.indexOf(partSchema);
                $scope.state.active = Math.min(iPart + 1, nParts - 1);
            };
            $scope.available = function(option) {
                if (!$scope.state.variables)
                    return false;
                return option.available($scope.state.variables);
            };
            $scope.isFinite = isFinite;

            $scope.checkRole = Authz({program: $scope.program});

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.which)) - 1;
                        i = Math.max(0, i);
                        i = Math.min($scope.rt.parts.length, i);
                        var partSchema = $scope.rt.parts[$scope.state.active];
                        var option = partSchema.options[i];
                        $scope.choose(partSchema, option);
                    }
                })
                .add({
                    combo: ['-', '_'],
                    description: "Previous response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.max(
                            0, $scope.state.active - 1);
                    }
                })
                .add({
                    combo: ['+', '='],
                    description: "Next response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.min(
                            $scope.rt.parts.length - 1,
                            $scope.state.active + 1);
                    }
                })
                .add({
                    combo: ['c'],
                    description: "Edit comment",
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('focus-comment');
                    }
                })
                .add({
                    combo: ['esc'],
                    description: "Stop editing comment (only in plain text mode)",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
        }
    }
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
                    ];
                }
            };
            $scope.addOption = function(part) {
                part.options.push({
                    score: 0,
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


.controller('ResponseTypeCtrl',
        function($scope, Authz, Measure, Current, layout, routeData,
            ResponseType) {

    $scope.layout = layout;
    $scope.checkRole = Authz({});
    $scope.responseType = routeData.responseType;
    $scope.ResponseType = ResponseType;
})

;
