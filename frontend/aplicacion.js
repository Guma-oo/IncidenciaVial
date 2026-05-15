const API = 'http://127.0.0.1:8000/api';

// Función para cambiar entre las 3 pantallas
function ver(id) {
    document.querySelectorAll('.vista').forEach(v => v.classList.remove('activa'));
    document.getElementById(id).classList.add('activa');
    if (id === 'panel') cargarPanel();
}

// Enviar datos al backend
async function enviar() {
    // 1. Recopilar los datos del reporte
    const data = {
        categoria: document.getElementById('cat').value,
        descripcion: document.getElementById('desc').value || "Sin descripción",
        direccion: document.getElementById('dir').value || "Sin dirección",
        prioridad: document.getElementById('prio').value,
        ciudadano: {
            nombres: document.getElementById('nom').value || "Anónimo",
            correo: document.getElementById('correo').value || "correo@anonimo.com",
            telefono: ""
        }
    };

    // 2. Crear la incidencia
    const res = await fetch(`${API}/incidencias/registrar`, {
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' }, 
        body: JSON.stringify(data)
    });
    
    if (res.ok) {
        const r = await res.json();
        const codigo = r.codigo_incidencia;

        // 3. Si hay un archivo seleccionado, enviarlo a la API de medios
        const inputArchivo = document.getElementById('archivoEvidencia');
        if (inputArchivo.files.length > 0) {
            const formData = new FormData();
            formData.append("archivo", inputArchivo.files[0]);

            // Llamada al endpoint unificado
            await fetch(`${API}/incidencias/${codigo}/subir-medio`, {
                method: 'POST',
                body: formData 
            });
        }

        alert(`¡Reporte enviado exitosamente!\nTu código es: ${codigo}`);
        
        // Limpiar el formulario
        document.getElementById('desc').value = '';
        document.getElementById('dir').value = '';
        inputArchivo.value = ''; 
    } else {
        alert("Error al enviar el reporte. Revisa la consola.");
    }
}

// Consultar una incidencia por código
async function buscar() {
    const cod = document.getElementById('codigo').value.trim();
    const div = document.getElementById('res-consulta');
    div.innerHTML = "Buscando...";
    
    const res = await fetch(`${API}/incidencias/${cod}`);
    if (res.ok) {
        const d = await res.json();
        let htmlContent = `
            <b>Código:</b> ${d.codigo_incidencia} <br> 
            <b>Estado:</b> ${d.estado.toUpperCase()} <br> 
            <b>Categoría:</b> ${d.categoria} <br> 
            <b>Descripción:</b> ${d.descripcion} <br>
        `;

        // Si tiene medios adjuntos, mostrarlos en la consulta
        if (d.medios && d.medios.length > 0) {
            htmlContent += `<br><b>Evidencias Adjuntas:</b><br>`;
            d.medios.forEach(medio => {
                htmlContent += `<a href="http://127.0.0.1:8000${medio.ruta}" target="_blank" class="media-link">📎 Ver ${medio.tipo}</a><br>`;
            });
        }

        div.innerHTML = htmlContent;
    } else {
        div.innerHTML = "<span style='color:red;'>No encontrado.</span>";
    }
}

// Cargar la lista del panel
async function cargarPanel() {
    const lista = document.getElementById('lista');
    lista.innerHTML = "Cargando...";
    
    const rEst = await fetch(`${API}/estadisticas`);
    if (rEst.ok) document.getElementById('tot').innerText = (await rEst.json()).total;

    const rInc = await fetch(`${API}/incidencias`);
    if (rInc.ok) {
        const data = await rInc.json();
        lista.innerHTML = data.map(i => {
            const mediaIcon = (i.medios && i.medios.length > 0) ? "📎 " : "";
            return `
            <div class="item">
                <b>${i.codigo_incidencia}</b> - <span style="color:#e85d26">${i.estado}</span><br>
                ${mediaIcon} ${i.categoria}: ${i.descripcion}
            </div>
            `;
        }).join('');
    } else {
        lista.innerHTML = "Error al cargar los datos.";
    }
}