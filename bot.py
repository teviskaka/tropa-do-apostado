import discord
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
                "pix": "Não configurado",
                "cargo_owner": None,
                "cat_vendas": None,   # Categoria para carrinhos
                "cat_suporte": None,  # Categoria para suporte/resgate
                "gif_url": ""
            },
            "produtos": {},
            "cupons": {}
        }
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

db = load_db()

# ================== BOT ==================
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

# ================== VIEWS DE TICKET ==================
class TicketActions(discord.ui.View):
    def __init__(self, cliente_id):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Deletando canal...")
        await interaction.channel.delete()

    @discord.ui.button(label="Mencionar Membro", style=discord.ButtonStyle.secondary, emoji="👤")
    async def mention(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🔔 Chamando <@{self.cliente_id}>!")

# ================== MODAL DE RESGATE ==================
class ModalResgate(discord.ui.Modal, title="Resgatar Produto"):
    codigo = discord.ui.TextInput(label="Código Único", placeholder="Cole seu código aqui...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cod = self.codigo.value.strip()
        cfg = db["config"]
        
        if not cfg["cat_suporte"]:
            return await interaction.response.send_message("❌ Categoria de suporte não configurada!", ephemeral=True)

        if cod in db["cupons"] and not db["cupons"][cod]["usado"]:
            info_produto = db["cupons"][cod]["produto"]
            db["cupons"][cod]["usado"] = True
            save_db(db)
            
            guild = interaction.guild
            categoria = guild.get_channel(int(cfg["cat_suporte"])) # USA CATEGORIA DE SUPORTE
            cargo_staff = guild.get_role(int(cfg["cargo_owner"]))
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                cargo_staff: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            
            canal = await guild.create_text_channel(name=f"resgate-{interaction.user.name}", category=categoria, overwrites=overwrites)
            
            embed = discord.Embed(
                title="✅ Resgate Validado!",
                description=f"**Produto:** {info_produto}\n**Código:** `{cod}`\n\n{cargo_staff.mention}, entregue o produto!",
                color=discord.Color.green()
            )
            if cfg["gif_url"]: embed.set_image(url=cfg["gif_url"])
            
            await canal.send(content=f"{interaction.user.mention} | {cargo_staff.mention}", embed=embed, view=TicketActions(interaction.user.id))
            await interaction.response.send_message(f"✅ Canal de resgate criado: {canal.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Código inválido ou já usado!", ephemeral=True)

# ================== PAINEL DE SUPORTE ==================
class PainelSuporte(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Suporte", style=discord.ButtonStyle.primary, emoji="📩", custom_id="btn_sup")
    async def suporte(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = db["config"]
        if not cfg["cat_suporte"]:
            return await interaction.response.send_message("❌ Categoria de suporte não configurada!", ephemeral=True)

        guild = interaction.guild
        categoria = guild.get_channel(int(cfg["cat_suporte"])) # USA CATEGORIA DE SUPORTE
        cargo_staff = guild.get_role(int(cfg["cargo_owner"]))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            cargo_staff: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        canal = await guild.create_text_channel(name=f"suporte-{interaction.user.name}", category=categoria, overwrites=overwrites)
        
        embed = discord.Embed(title="Atendimento", description="Aguarde um atendente.", color=discord.Color.blue())
        if cfg["gif_url"]: embed.set_image(url=cfg["gif_url"])
        
        await canal.send(content=f"{interaction.user.mention} | {cargo_staff.mention}", embed=embed, view=TicketActions(interaction.user.id))
        await interaction.response.send_message(f"✅ Ticket criado: {canal.mention}", ephemeral=True)

    @discord.ui.button(label="Resgatar Compra", style=discord.ButtonStyle.success, emoji="🎁", custom_id="btn_res")
    async def resgatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalResgate())

# ================== SISTEMA DE VENDAS ORIGINAL ==================
class RedirectView(discord.ui.View):
    def __init__(self, url):
        super().__init__()
        self.add_item(discord.ui.Button(label="Clique aqui", url=url, style=discord.ButtonStyle.link))

class AdminActions(discord.ui.View):
    def __init__(self, cliente_id, produto_nome, cargo_id):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id
        self.produto = produto_nome
        self.cargo_id = cargo_id

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == db["config"]["cargo_owner"] for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        codigo = f"Resgatar{str(uuid.uuid4())[:8]}"
        db["cupons"][codigo] = {"produto": self.produto, "usado": False}
        save_db(db)

        membro = interaction.guild.get_member(self.cliente_id)
        cargo = interaction.guild.get_role(self.cargo_id)

        if membro and cargo:
            await membro.add_roles(cargo)
            await interaction.response.send_message(f"✅ Pagamento aprovado!\n🔑 Código: `{codigo}`")
        else:
            await interaction.response.send_message("Erro ao entregar.", ephemeral=True)

    @discord.ui.button(label="Fechar Carrinho", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

class BuyView(discord.ui.View):
    def __init__(self, produto_nome, cargo_id):
        super().__init__(timeout=None)
        self.produto = produto_nome
        self.cargo_id = cargo_id

    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = db["config"]
        if not cfg["cat_vendas"]:
            return await interaction.response.send_message("❌ Categoria de Vendas não configurada!", ephemeral=True)

        guild = interaction.guild
        categoria = guild.get_channel(int(cfg["cat_vendas"])) # USA CATEGORIA DE VENDAS
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(cfg["cargo_owner"]): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        canal = await guild.create_text_channel(name=f"🛒-{interaction.user.name}", category=categoria, overwrites=overwrites)
        dados = db["produtos"][self.produto]
        embed = discord.Embed(title="💳 Checkout", color=discord.Color.blue())
        embed.add_field(name="📦 Produto", value=self.produto)
        embed.add_field(name="💰 Valor", value=f"R$ {dados['preco']}")
        embed.add_field(name="🔑 PIX", value=f"`{cfg['pix']}`")
        if dados.get("imagem"): embed.set_thumbnail(url=dados.get("imagem"))
        
        await canal.send(content=interaction.user.mention, embed=embed, view=AdminActions(interaction.user.id, self.produto, self.cargo_id))
        await interaction.response.send_message(f"✅ Carrinho criado", view=RedirectView(canal.jump_url), ephemeral=True)

# ================== COMANDOS DE CONFIGURAÇÃO ==================

@bot.tree.command(name="config-vendas", description="Define a categoria onde os carrinhos de COMPRA serão abertos")
async def config_vendas(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    db["config"]["cat_vendas"] = categoria.id
    save_db(db)
    await interaction.response.send_message(f"✅ Categoria de **VENDAS** definida: {categoria.name}", ephemeral=True)

@bot.tree.command(name="config-suporte", description="Define a categoria onde o SUPORTE e RESGATE serão abertos")
async def config_suporte(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    db["config"]["cat_suporte"] = categoria.id
    save_db(db)
    await interaction.response.send_message(f"✅ Categoria de **SUPORTE** definida: {categoria.name}", ephemeral=True)

@bot.tree.command(name="setup", description="Configura PIX e Cargo Staff")
async def setup(interaction: discord.Interaction, pix: str, cargo_admin: discord.Role):
    db["config"]["pix"] = pix
    db["config"]["cargo_owner"] = cargo_admin.id
    save_db(db)
    await interaction.response.send_message("✅ Configurações básicas salvas!", ephemeral=True)

# ================== COMANDOS DE PAINEL E PRODUTO ==================

@bot.tree.command(name="enviar_painel", description="Envia o painel de Suporte/Resgate")
async def enviar_painel(interaction: discord.Interaction, canal: discord.TextChannel, gif_url: str):
    db["config"]["gif_url"] = gif_url
    save_db(db)
    embed = discord.Embed(title="Central de Atendimento", description="📩 Suporte | 🎁 Resgatar Compra", color=0x2b2d31)
    embed.set_image(url=gif_url)
    await canal.send(embed=embed, view=PainelSuporte())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)

@bot.tree.command(name="produtor", description="Cria um produto no banco")
async def produtor(interaction: discord.Interaction):
    class ProdModal(discord.ui.Modal, title="Criar Produto"):
        nome = discord.ui.TextInput(label="Nome")
        desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)
        preco = discord.ui.TextInput(label="Preço")
        estoque = discord.ui.TextInput(label="Estoque")
        imagem = discord.ui.TextInput(label="Link Imagem", required=False)
        async def on_submit(self, interaction: discord.Interaction):
            db["produtos"][self.nome.value] = {"desc": self.desc.value, "preco": self.preco.value, "estoque": self.estoque.value, "imagem": self.imagem.value}
            save_db(db)
            await interaction.response.send_message(f"✅ Produto {self.nome.value} criado!", ephemeral=True)
    await interaction.response.send_modal(ProdModal())

@bot.tree.command(name="addprodutor", description="Anuncia um produto")
async def addprodutor(interaction: discord.Interaction, nome_do_produto: str, canal: discord.TextChannel, cargo: discord.Role):
    if nome_do_produto not in db["produtos"]: return await interaction.response.send_message("❌ Erro.", ephemeral=True)
    dados = db["produtos"][nome_do_produto]
    embed = discord.Embed(title="🛒 " + nome_do_produto, description=dados["desc"], color=discord.Color.green())
    embed.add_field(name="💰 Preço", value=f"R$ {dados['preco']}")
    if dados.get("imagem"): embed.set_image(url=dados["imagem"])
    await canal.send(embed=embed, view=BuyView(nome_do_produto, cargo.id))
    await interaction.response.send_message("✅ Postado!", ephemeral=True)

# ================== RUN ==================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
