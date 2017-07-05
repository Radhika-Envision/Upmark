'use strict'

angular.module('vpac.utils.requests', [])


.factory('paged', [function() {
    return function(response) {
        var data = response.resource;
        data.$pageIndex = parseInt(response.headers('Page-Index'));
        data.$pageItemCount = parseInt(response.headers('Page-Item-Count'));
        data.$pageCount = parseInt(response.headers('Page-Count'));
        return data;
    };
}])

.factory('download', function($http) {
    return function(namePattern, url, postData) {
        var fileName;
        if (namePattern.exec) {
            var match = namePattern.exec(url);
            if (!match)
                throw "Can't determine download name";
            fileName = match[1];
        } else {
            fileName = namePattern;
        }

        var success = function success(response) {
            var message = "Export finished.";
            if (response.headers('Operation-Details'))
                message += ' ' + response.headers('Operation-Details');
            var blob = new Blob(
                [response.data], {type: response.headers('Content-Type')});
            saveAs(blob, fileName);
            return response;
        };

        if (postData) {
            return $http.post(url, postData, {
                responseType: "arraybuffer", cache: false
            }).then(success);
        } else {
            return $http.get(url, {
                responseType: "arraybuffer", cache: false
            }).then(success);
        };
    };
});
