'use strict';

angular.module('upmark.submission.export', [])


.controller('SubmissionExportCtrl', function(
        $scope, $location, Notifications, LocationSearch, Enqueue) {

    $scope.startCalender = {
      opened: false
    };
    $scope.endCalender = {
      opened: false
    };
    $scope.dateOptions = {
      format: 'MMM yyyy',
      altInputFormats: ['mediumDate', 'dd MMM yyyy', 'MMM yyyy', 'yyyy', 'yyyy-MM-dd'],
      formatYear: 'yyyy',
      startingDay: 1,
    };

    $scope.openStartCalender = function() {
        $scope.startCalender.opened = true;
    };
    $scope.openEndCalender = function() {
        $scope.endCalender.opened = true;
    };

    // Report type
    $scope.$watch('reportSpec.type', function(type) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        }

        if (type == 'summary') {
            $scope.reportSpec.organisationId = $scope.submission.organisation.id;
        } else {
            $scope.reportSpec.organisationId = null;
        };
    });

    // Date range and interval settings
    $scope.$watch('reportForm.min_date', function(min) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        };

        $scope.reportSpec.minDate = min.getTime() / 1000;
    });
    $scope.$watch('reportForm.max_date', function(max) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        };

        $scope.reportSpec.maxDate = max.getTime() / 1000;
    });
    $scope.$watch('reportForm.intervalNum', function(num) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        }

        // Interval length must be a positive integer
        if (num <= 0.0) {
            $scope.reportForm.intervalNum = null;
        };
        if (num % 1 != 0.0) {
            $scope.reportForm.intervalNum = Math.floor(num)
        };

        // Write to reportSpec
        if ($scope.reportForm.intervalNum != null) {
            $scope.reportSpec.intervalNum = $scope.reportForm.intervalNum;
        } else {
            $scope.reportSpec.intervalNum = 1.0;
        };
    });
    $scope.$watch('reportSpec.intervalUnit', function(unit) {
        if (unit.id == 'months')
            $scope.dateOptions.format = 'MMM yyyy';
        else
            $scope.dateOptions.format = 'yyyy';
    });

    // Location filter settings
    $scope.searchLoc = function(term) {
        return LocationSearch.query({term: term}).$promise;
    };
    $scope.deleteLocation = function(i) {
        $scope.reportForm.locations.splice(i, 1);
    };
    $scope.$watch('reportForm.locations', function(loc) {
        if (!$scope.reportForm || !$scope.reportSpec) {
          return;
        }

        $scope.reportSpec.locations = loc
    })

    // Organisation size filter settings
    $scope.$watch('reportSpec.minInternalFtes', function(ftes) {
        if (!$scope.reportSpec) {
            return
        };
        if (ftes <= 0) {
            $scope.reportSpec.minInternalFtes = null;
            return
        };
        if (ftes != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxInternalFtes', function(ftes) {
        if (!$scope.reportSpec) {
            return
        };
        if (ftes <= 0) {
            $scope.reportSpec.maxInternalFtes = null;
            return
        };
        if (ftes != null) {
            $scope.reportSpec.filterSize = true;
        };

    });
    $scope.$watch('reportSpec.minContractors', function(contractors) {
        if (!$scope.reportSpec) {
            return
        };
        if (contractors <= 0) {
            $scope.reportSpec.minContractors = null;
        };
        if (contractors != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxExternalFtes', function(contractors) {
        if (!$scope.reportSpec) {
            return
        };
        if (contractors <= 0) {
            $scope.reportSpec.maxExternalFtes = null;
        };
        if (contractors != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.minEmployees', function(employees) {
        if (!$scope.reportSpec) {
            return
        };
        if (employees <= 0) {
            $scope.reportSpec.minEmployees = null;
        };
        if (employees != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxEmployees', function(employees) {
        if (!$scope.reportSpec) {
            return
        };
        if (employees <= 0) {
            $scope.reportSpec.maxEmployees = null;
        };
        if (employees != null) {
            $scope.reportSpec.filterSize = true;
        };

    });
    $scope.$watch('reportSpec.minPopulation', function(population) {
        if (!$scope.reportSpec) {
            return
        };
        if (population <= 0) {
            $scope.reportSpec.minPopulation = null;
        };
        if (population != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxPopulation', function(population) {
        if (!$scope.reportSpec) {
            return
        };
        if (population <= 0) {
            $scope.reportSpec.maxPopulation = null;
        };
        if (population != null) {
            $scope.reportSpec.filterSize = true;
        };
    });

    // Approval status filter
    $scope.setReportApproval = function(state) {
        $scope.reportSpec.approval = state;
    }

    // Report form
    $scope.openReportForm = function() {
        if (!$scope.reportForm) {
            var dt = new Date();
            dt.setFullYear(dt.getFullYear() - 1);
            $scope.reportForm = {
                intervalUnits: [
                    {name: 'Months', id: 'months'},
                    {name: 'Years', id: 'years'}],
                intervalNum: 1.0,
                allowedStates: ['reviewed', 'approved'],
                locations: [],
                min_date: dt,
                max_date: new Date()
            }

            if ($scope.checkRole('report_temporal_full'))
                $scope.reportForm.allowedStates = null;

        } else {
                $scope.reportForm.open = true;
        };

        if (!$scope.reportSpec) {
            // Initial report spec
            $scope.reportSpec = {
                type: 'summary',
                minDate: null,
                maxDate: null,
                intervalNum: null,
                intervalUnit: $scope.reportForm.intervalUnits[0],
                filterSize: false,
                minConstituents: 5,
                minInternalFtes: null,
                maxInternalFtes: null,
                minContractors: null,
                maxExternalFtes: null,
                minEmployees: null,
                maxEmployees: null,
                minPopulation: null,
                maxPopulation: null,
                quality: 0,
                approval: 'reviewed',
                locations: null,
                organisationId: null
            };
        };
    };

    $scope.closeReportForm = function() {
        $scope.reports.formOpen = false;
        $scope.reportForm = null;
        $scope.reportSpec = null;
        $scope.startCalender.opened = false;
        $scope.endCalender.opened = false;
    }

    // Report form exporter
    $scope.specTest = function(spec) {
        // Test start and end dates are sensible
        if (spec.minDate >= spec.maxDate) {
            alert("Invalid input: start date equal to or later than end date");
            return false;
        }

        // Test min/max pairs are sensible if set
        return true;
    };

    $scope.downloadTemporalReport = Enqueue(function(query, file_type, survey_id) {
        if (!$scope.specTest(query))
            return;
        var fileName = 'submission-temporal.' + file_type;
        var url = '/report/sub/temporal/' + survey_id + '.' + file_type;
        query = angular.copy(query);
        query.intervalUnit = query.intervalUnit.id;
        $scope.download(fileName, url, query);
    }, 500, $scope);

    $scope.openReportForm();
})

;
