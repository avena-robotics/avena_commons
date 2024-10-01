let cpuChart, memChart, diskChart;
let coreCharts = [];
let countdownInterval;

$(document).ready(function () {
    $('#cpu-button, #return-button').click(function (e) {
        e.preventDefault();
        const url = $(this).attr('id') === 'cpu-button' ? '/content/cpu' : '/content/index';
        loadContent(url);
    });

    function loadContent(url) {
        $.ajax({
            url: url,
            type: 'GET',
            success: function (response) {
                $('#content').html(response);
                if (url === '/content/cpu') {
                    $('.return-button').css('display', 'block');
                } else {
                    $('.return-button').css('display', 'none');
                }
            },
            error: function () {
                console.error("Failed to load content from", url);
            }
        });
    }
});

function createChart(chartElement, data) {
    let backgroundColor;
    if (data > 80) {
        backgroundColor = '#f04e4e';
    } else if (data > 40) {
        backgroundColor = '#f0ad4e';
    } else {
        backgroundColor = '#5cb85c';
    }

    const ctx = chartElement.getContext('2d');
    const chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [data, 100 - data],
                backgroundColor: [backgroundColor, '#eaeaea'],
                borderWidth: 0,
            }]
        },
        options: {
            animation: false,
            responsive: true,
            cutoutPercentage: 80,
            legend: {
                display: false
            },
            tooltips: {
                enabled: false
            }
        }
    });
    return chart;
}

function updateCharts() {
    if (data) {
        if (cpuChart) {
            cpuChart.destroy();
        }
        if (memChart) {
            memChart.destroy();
        }
        if (diskChart) {
            diskChart.destroy();
        }
        for (let i = 0; i < data.cpu_info['cpu_usage_per_core'].length; i++) {
            if (coreCharts[i]) {
                coreCharts[i].destroy();
            }
            if (document.getElementById('core-chart-' + i)) {
                console.log('core-chart-' + i);
                console.log(data.cpu_info['cpu_usage_per_core'][i]);
                coreCharts[i] = createChart(document.getElementById('core-chart-' + i), data.cpu_info['cpu_usage_per_core'][i], 'Core ' + i, '#5cb85c');
            }
        }

        if (document.getElementById('cpu-chart')) {
            cpuChart = createChart(document.getElementById('cpu-chart'), data.cpu_info['total_cpu_usage'], 'CPU', '#5cb85c');
        }
        if (document.getElementById('memory-chart')) {
            memChart = createChart(document.getElementById('memory-chart'), data.memory_info['memory_percentage'], 'Memory', '#f0ad4e');
        }
        if (document.getElementById('disk-chart')) {
            diskChart = createChart(document.getElementById('disk-chart'), data.disk_info['/']['usage_percentage'], 'Disk', '#f0ad4e');
        }
    }
}

function updateData() {
    $.ajax({
        url: "/data",
        type: "GET",
        dataType: "json",
        success: function (responseData) {
            data = responseData;
            warning_flag = false;

            if (document.getElementById('cpu-core-0')) {
                const topProcessesPerCore = {};
                data.process_info.forEach(process => {
                    if (!topProcessesPerCore[process.cpu_num]) {
                        topProcessesPerCore[process.cpu_num] = [];
                    }
                    topProcessesPerCore[process.cpu_num].push(process);
                });

                Object.keys(topProcessesPerCore).forEach(core => {
                    topProcessesPerCore[core] = topProcessesPerCore[core]
                        .sort((a, b) => b.cpu_percent - a.cpu_percent)
                        .slice(0, 3);
                });

                Object.keys(topProcessesPerCore).forEach(core => {
                    topProcessesPerCore[core].forEach((process, index) => {
                        if (process.cmdline === '') {
                            process.cmdline = 'Unknown';
                        }
                        else if (process.cmdline[0] === 'python3') {
                            process.cmdline = process.cmdline[1];
                        }
                        else if (process.cmdline[1] === 'python3') {
                            process.cmdline = process.cmdline[2];
                        }
                        else {
                            process.cmdline = process.cmdline[1];
                        }
                        $(`#top-process-${core}-${index + 1}`).text(`Top ${index + 1} name: ${process.cmdline}, usage: ${process.cpu_percent}%`);
                    });
                });
                $.each(data.cpu_info['cpu_usage_per_core'], function (core, usage) {
                    $('#cpu-core-' + core + ' #cpu-usage-detailed').text(usage + '%');

                    if (usage > 80) {
                        $('#data-div-core-' + core).removeClass('div-color-normal');
                        $('#data-div-core-' + core).addClass('div-color-error');
                        warning_flag = true;
                    }
                    if (usage > 50) {
                        $('#data-div-core-' + core).removeClass('div-color-normal');
                        $('#data-div-core-' + core).addClass('div-color-warning');
                    }
                    else {
                        $('#data-div-core-' + core).removeClass('div-color-error');
                        $('#data-div-core-' + core).removeClass('div-color-warning');
                        $('#data-div-core-' + core).addClass('div-color-normal');
                    }
                });
            }
            $("#cpu-usage").text(data.cpu_info['total_cpu_usage'] + "%");
            $("#memory-usage").text(data.memory_info['memory_percentage'] + "%");
            $("#disk-usage").text(data.disk_info['/']['usage_percentage'] + "%");
            $("#msg").text(data.msg);

            if (warning_flag === true) {
                $("#msg").removeClass("alert-ok").addClass("alert-warning");
                $("#msg").text("System Status: Warning - CPU usage is above 80%");
            }
            else if (data.msg === "Warning") {
                $("#msg").removeClass("alert-ok").addClass("alert-warning");
                $("#msg").text("System Status: Warning - CPU or Memory usage is above 80%");
            } else {
                $("#msg").removeClass("alert-warning").addClass("alert-ok");
                $("#msg").text("System Status: Everything is running smoothly.");
            }
            updateCharts();
        },
        error: function () {
            console.log("Error fetching data.");
        }
    });
}

updateData();
setInterval(updateData, 1000);