(() => {
    const url = "https://api.open-meteo.com/v1/forecast?latitude=46.84&longitude=29.64&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,pressure_msl&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max&forecast_days=5&timezone=Europe%2FChisinau";
    const names = {
        0:"Ясно",1:"Преимущественно ясно",2:"Переменная облачность",3:"Пасмурно",
        45:"Туман",48:"Туман",51:"Морось",53:"Морось",55:"Сильная морось",
        61:"Небольшой дождь",63:"Дождь",65:"Сильный дождь",71:"Небольшой снег",
        73:"Снег",75:"Сильный снег",80:"Кратковременный дождь",81:"Ливни",
        82:"Сильные ливни",85:"Снегопад",86:"Сильный снегопад",
        95:"Гроза",96:"Гроза с градом",99:"Сильная гроза"
    };
    const el = id => document.getElementById(id);
    const n = value => Number.isFinite(value) ? Math.round(value) : "—";

    async function updateWeather() {
        try {
            const response = await fetch(url, {cache:"no-store"});
            if (!response.ok) throw new Error("HTTP " + response.status);
            const data = await response.json();
            const c = data.current;
            el("weather-current").innerHTML =
                `<div class="weather-temp">${n(c.temperature_2m)}°C</div>` +
                `<div class="weather-description">${names[c.weather_code] || "Погодные условия"}</div>` +
                `<p>Ощущается как ${n(c.apparent_temperature)}°C</p>`;
            el("weather-details").innerHTML = [
                ["Влажность", n(c.relative_humidity_2m) + "%"],
                ["Ветер", n(c.wind_speed_10m) + " км/ч"],
                ["Давление", n(c.pressure_msl) + " гПа"]
            ].map(([a,b]) => `<div class="weather-detail"><span>${a}</span><strong>${b}</strong></div>`).join("");

            const d = data.daily;
            el("weather-forecast").innerHTML = d.time.map((day,i) => {
                const date = new Date(day + "T12:00:00").toLocaleDateString("ru-RU",{weekday:"short",day:"numeric",month:"short"});
                return `<article class="forecast-day"><div><div class="forecast-date">${date}</div><div class="forecast-desc">${names[d.weather_code[i]] || "Переменная погода"} · осадки ${n(d.precipitation_probability_max[i])}%</div></div><div class="forecast-temps">${n(d.temperature_2m_max[i])}°<small>${n(d.temperature_2m_min[i])}° ночью</small></div></article>`;
            }).join("");
            el("weather-updated").textContent = "Обновлено " + new Date().toLocaleTimeString("ru-RU",{hour:"2-digit",minute:"2-digit"});
        } catch (error) {
            el("weather-current").textContent = "Не удалось загрузить погоду";
            el("weather-forecast").textContent = "Проверьте подключение к Open-Meteo.";
            el("weather-updated").textContent = "Нет данных";
            console.error("Weather:", error);
        }
    }
    updateWeather();
    setInterval(updateWeather, 30 * 60 * 1000);
})();
