import os
import io
import base64
import pandas as pd
import matplotlib.pyplot as plt
from sideseeing_tools import sideseeing
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, Template
from typing import List, Dict, Tuple, Optional

class Report:

    DEFAULT_TEMPLATE = "templates/t2.html"

    def __init__(self, default_template_path: str = DEFAULT_TEMPLATE):
        """
        Inicializa o Report com um template padrão.
        """
        self.default_template_path = default_template_path
        self._validate_template_exists(default_template_path)

    def _validate_template_exists(self, template_path: str) -> None:
        """Valida se o template existe."""
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"O Template {template_path} não foi encontrado.")

    def _load_template(self, template_path: Optional[str] = None) -> Template:
        """Carrega um template, seja o padrão ou um personalizado."""
        path = template_path or self.default_template_path
        self._validate_template_exists(path)
        
        template_dir = os.path.dirname(path) or '.'
        template_file_name = os.path.basename(path)
        
        env = Environment(loader=FileSystemLoader(template_dir))
        return env.get_template(template_file_name)

    def _load_sideseeing_data(self, dir_path: str) -> Tuple[str, sideseeing.SideSeeingDS]:
        """
        Carrega o dataset usando a sideseeing-tools.
        """
        if not os.path.isdir(dir_path):
            raise NotADirectoryError(f"O caminho especificado não é um diretório: {dir_path}")
            
        ds = sideseeing.SideSeeingDS(root_dir=dir_path)
        title = f"Relatório de '{os.path.basename(dir_path)}'"
        return title, ds


    def _create_summary(self, ds: sideseeing.SideSeeingDS) -> Dict:
        """
        Gera um dicionário com dados de resumo do dataset.
        """
        print("Gerando resumo do dataset...")
        summary_data = {}

        # 1. Obter o DataFrame de metadados
        # O método metadata() gera ou carrega um CSV com infos de cada instância
        metadata_df = ds.metadata()

        # 2. Extrair estatísticas
        if not metadata_df.empty:
            summary_data['total_instances'] = ds.size # ds.size retorna o número de instâncias
            summary_data['total_duration_seconds'] = metadata_df['media_total_time'].sum()
            summary_data['devices'] = metadata_df['model'].unique().tolist()
            summary_data['android_versions'] = metadata_df['so_version'].unique().tolist()
        else:
            summary_data['total_instances'] = 0
            summary_data['total_duration_seconds'] = 0
            summary_data['devices'] = []
            summary_data['android_versions'] = []

        # 3. Listar os tipos de sensores encontrados
        sensor_types = []
        for n_axis, sensors in ds.sensors.items():
            if sensors: # Verifica se há sensores nesse grupo
                sensor_types.extend(list(sensors.keys()))
        summary_data['sensor_types'] = sensor_types
        
        return summary_data

    def _process_sensors_data(self, ds: sideseeing.SideSeeingDS) -> Optional[str]:
        """
        Processa os dados de sensores, gerando um gráfico para cada tipo de sensor
        encontrado no dataset.
        """
        print("Processando dados de sensores...")
        html_components = []
        
        # Dicionário que mapeia o tipo de sensor para suas colunas de eixos
        axis_map = {
            'sensors1': ['x'],
            'sensors3': ['x', 'y', 'z'],
            'sensors6': ['x', 'y', 'z', 'dx', 'dy', 'dz']
        }

        # O ds.sensors nos dá um dicionário com todos os sensores disponíveis
        sensor_inventory = ds.sensors

        # Itera sobre os tipos de sensor ('sensors1', 'sensors3', etc.)
        for n_axis, sensors in sensor_inventory.items():
            if not sensors: # Pula se não houver sensores deste tipo (ex: nenhum sensor de 6 eixos)
                continue
            
            # Pega as colunas correspondentes a este tipo de sensor
            axis_columns = axis_map.get(n_axis)
            if not axis_columns:
                continue

            # Itera sobre cada nome de sensor específico (ex: 'acelerômetro')
            for sensor_name, instance_names_set in sensors.items():
                
                # Prepara os dados para plotagem, coletando de cada instância
                data_to_plot = []
                for instance_name in sorted(list(instance_names_set)):
                    instance = ds.instances[instance_name]
                    
                    # Acessa o dicionário de sensores do tipo correto (ex: instance.sensors3)
                    sensor_data_dict = getattr(instance, n_axis, {})
                    
                    # Pega o DataFrame do sensor específico
                    df = sensor_data_dict.get(sensor_name)

                    if df is not None and not df.empty:
                        data_to_plot.append({
                            'instance_name': instance.name,
                            'sensor_data': df
                        })
                
                if not data_to_plot:
                    continue

                # --- Recriando a lógica de plot_sensors para capturar a imagem ---
                html_components.append(f"<hr><h3>Sensor: {sensor_name}</h3>")
                
                # Cria uma figura com um subplot para cada instância que tem este sensor
                fig, axes = plt.subplots(
                    nrows=len(data_to_plot), 
                    ncols=1, 
                    figsize=(15, len(data_to_plot) * 4), # Altura dinâmica
                    sharex=True, 
                    squeeze=False # Garante que 'axes' seja sempre 2D
                )

                for i, item in enumerate(data_to_plot):
                    ax = axes[i, 0] # Acessa o subplot
                    sensor_df = item['sensor_data']
                    
                    # Plota cada eixo no subplot
                    for col in axis_columns:
                        ax.plot(sensor_df['Time (s)'], sensor_df[col], label=col, linewidth=0.8)
                    
                    ax.set_title(item['instance_name'])
                    ax.set_ylabel('Valor')
                    ax.legend()
                    ax.grid(True)
                
                axes[-1, 0].set_xlabel('Tempo (s)') # Adiciona label de tempo apenas no último gráfico
                
                plt.tight_layout(rect=[0, 0.03, 1, 0.98]) # Ajusta layout para o título principal

                # --- Converte o gráfico para base64 e insere no HTML ---
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight')
                plt.close(fig)
                img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                html_components.append(f'<img src="data:image/png;base64,{img_base64}" class="img-fluid mb-4"/>')

        if not html_components:
            return "<p>Nenhum dado de sensor processável foi encontrado no dataset.</p>"

        return "\n".join(html_components)

    def generate_report(self, dir_path: str, output_path: str, template_path: Optional[str] = None):
        """
        Gera um relatório HTML completo a partir de um diretório de dados.
        """
        print(f"Lendo o diretório: {dir_path}")
        title, ds = self._load_sideseeing_data(dir_path)

        summary = self._create_summary(ds)

        # Processa as diferentes seções do relatório
        sections = {
            'sensor': self._process_sensors_data(ds)
            # Futuramente:
            # 'geo': self._process_geo_data(ds),
            # 'images': self._process_images_data(ds)
        }
        
        # Filtra seções que não foram processadas
        processed_sections = {key: value for key, value in sections.items() if value is not None}

        print("Carregando template...")
        template = self._load_template(template_path)

        context = {
            "title": title,
            "sections": processed_sections,
            "summary": summary, 
            "data_geracao": datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        }

        html_output = template.render(context)

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_output)
        
        print(f"Relatório salvo com sucesso em: {output_path}")

dir_path = '/home/renzo/Documents/GitHub/temp-SideSeeing-Exporter/dataset'
out_path = '/home/renzo/Documents/GitHub/temp-SideSeeing-Exporter/out/1.html'
r = Report()
r.generate_report(dir_path, out_path)




