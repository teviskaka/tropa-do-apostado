import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import uuid

# ================== ARQUIVO DB ==================
DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "config": {
                "cargo_owner": None,
                "cat_suporte": None
            },
            "cupons": {}
        }
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

db = load_db()

# ================== MODAL DE RESGATE ==================
class ModalResgate(discord.ui.Modal, title="Resgatar Produto"):
    codigo = discord.ui.TextInput(label="Insira o código único", placeholder="Resgatar...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cod = self.codigo.value.strip()
        
        if cod in db["cupons"] and not db["cupons"][cod]["usado"]:
            db["cupons"][cod]["usado"] = True
            save_db(db)
            
            cargo_id = db["config"]["cargo_owner"]
            mencao = f"<@&{cargo_id}>" if cargo_id else "@Owner"
            
            await interaction.response.send_message(
                f"✅ **Código Validado!**\nO usuário {interaction.user.mention} usou o código `{cod}`.\n"
                f"🔔 {mencao}, envie o produto do cliente aqui!"
            )
        else:
            await interaction.response.send_message("❌ Código inválido ou já utilizado.", ephemeral=True)

# ================== VIEW INTERNA DO TICKET ==================
class TicketActions(discord.ui.View):
    def __init__(self, cliente_id):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Encerrando ticket...")
        await interaction.channel.delete()

    @discord.ui.button(label="Mencionar Membro", style=discord.ButtonStyle.secondary, emoji="👤")
    async def mencao(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🔔 Chamando {interaction.guild.get_member(self.cliente_id).mention}!")

# ================== VIEW PRINCIPAL (PAINEL) ==================
class PainelSuporte(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Suporte", style=discord.ButtonStyle.primary, emoji="📩", custom_id="btn_suporte")
    async def suporte(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = db["config"]
        if not cfg["cat_suporte"]:
            return await interaction.response.send_message("Sistema não configurado!", ephemeral=True)

        guild = interaction.guild
        categoria = guild.get_channel(cfg["cat_suporte"])
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(cfg["cargo_owner"]): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        canal = await guild.create_text_channel(
            name=f"suporte-{interaction.user.name}",
            category=categoria,
            overwrites=overwrites
        )

        embed = discord.Embed(title="Atendimento", description="Aguarde o suporte.", color=discord.Color.blue())
        await canal.send(embed=embed, view=TicketActions(interaction.user.id))
        await interaction.response.send_message(f"✅ Ticket aberto em {canal.mention}", ephemeral=True)

    @discord.ui.button(label="Resgatar Compra", style=discord.ButtonStyle.success, emoji="🎁", custom_id="btn_resgate")
    async def resgate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalResgate())

# ================== BOT CLASS ==================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(PainelSuporte())
        await self.tree.sync()

bot = MyBot()

# ================== COMANDOS ==================

@bot.tree.command(name="setup_suporte", description="Envia o painel de suporte")
async def setup_suporte(interaction: discord.Interaction, canal: discord.TextChannel, categoria: discord.CategoryChannel, cargo_admin: discord.Role):
    db["config"]["cargo_owner"] = cargo_admin.id
    db["config"]["cat_suporte"] = categoria.id
    save_db(db)
    
    embed = discord.Embed(title="Central de Atendimento", description="Escolha uma opção abaixo:", color=discord.Color.green())
    await canal.send(embed=embed, view=PainelSuporte())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)

@bot.tree.command(name="gerar_codigo", description="Gera um código de resgate único")
async def gerar_codigo(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Sem permissão.", ephemeral=True)
    
    codigo_unico = f"Resgatar{str(uuid.uuid4())[:8]}"
    db["cupons"][codigo_unico] = {"usado": False}
    save_db(db)
    
    await interaction.response.send_message(f"✅ Código: `{codigo_unico}`", ephemeral=True)

# ================== RUN ==================
TOKEN = os.getenv("TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO: O Token não foi encontrado nas variáveis de ambiente do Railway!")
